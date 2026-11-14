"""Real socket tests for the installer-only proxy; no Android or public network."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SetupDownloadProxyTests(unittest.TestCase):
    def test_bound_routing_authentication_limits_and_cancellation(self):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').is_file() else shutil.which('javac')
        java = str(jdk / 'java') if (jdk / 'java').is_file() else shutil.which('java')
        keytool = str(jdk / 'keytool') if (jdk / 'keytool').is_file() else shutil.which('keytool')
        if not javac or not java or not keytool:
            self.skipTest('A JDK is required')
        with tempfile.TemporaryDirectory(prefix='z8-proxy-tests-') as temporary:
            directory = Path(temporary)
            # Real TLS with one explicit fixture trust anchor. Production keeps
            # the platform default trust store; no permissive verifier is used.
            for name in ('trusted', 'untrusted'):
                generated = subprocess.run([keytool, '-genkeypair', '-alias', name, '-keyalg', 'RSA',
                    '-keystore', str(directory / (name + '.p12')), '-storetype', 'PKCS12', '-storepass', 'fixturepass',
                    '-keypass', 'fixturepass', '-dname', 'CN=ports.ubuntu.com', '-validity', '2',
                    '-ext', 'SAN=dns:ports.ubuntu.com,dns:archive.ubuntu.com,dns:deb.debian.org'],
                    capture_output=True, text=True, timeout=30)
                self.assertEqual(0, generated.returncode, generated.stdout + generated.stderr)
            files = []
            for name, source in STUBS.items():
                path = directory / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source)
                files.append(str(path))
            probe = directory / 'ProxyProbe.java'
            probe.write_text(PROBE)
            source = ROOT / 'overlay/app/src/main/java/com/termux/app/Z8SetupDownloadProxy.java'
            built = subprocess.run([javac, str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), '-encoding', 'UTF-8', '-d', str(directory), str(source), str(probe), *files],
                                   text=True, capture_output=True, timeout=45)
            self.assertEqual(0, built.returncode, built.stdout + built.stderr)
            run = subprocess.run([java, '-Djavax.net.ssl.trustStore=' + str(directory / 'trusted.p12'),
                                 '-Djavax.net.ssl.trustStorePassword=fixturepass',
                                 '-cp', str(directory), 'com.termux.app.ProxyProbe',
                                 str(directory / 'trusted.p12'), str(directory / 'untrusted.p12')],
                                 text=True, capture_output=True, timeout=35)
            self.assertEqual(0, run.returncode, run.stdout + run.stderr)
            self.assertIn('PASS: installer proxy', run.stdout)


STUBS = {
    'android/content/Context.java': 'package android.content; public class Context {}',
    'android/net/Network.java': '''package android.net;
        public class Network {
            public javax.net.SocketFactory getSocketFactory() {return javax.net.SocketFactory.getDefault();}
            public java.net.InetAddress[] getAllByName(String host) throws java.io.IOException {return java.net.InetAddress.getAllByName(host);}
        }
    ''',
}

PROBE = r'''
package com.termux.app;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import javax.net.SocketFactory;
import javax.net.ssl.*;
import java.security.KeyStore;

public class ProxyProbe {
    static final InetAddress LOCAL;
    static {try {LOCAL=InetAddress.getByName("127.0.0.1");} catch(Exception e){throw new RuntimeException(e);}}
    static int checks;
    static void check(boolean condition,String why) {if(!condition)throw new AssertionError(why);checks++;}
    static String header(InputStream input)throws IOException {
        ByteArrayOutputStream bytes=new ByteArrayOutputStream();int state=0;
        while(state!=4) {int value=input.read();if(value==-1)throw new EOFException();bytes.write(value);
            if(state==0||state==2)state=value=='\r'?state+1:0;else state=value=='\n'?state+1:0;}
        return bytes.toString(StandardCharsets.US_ASCII.name());
    }
    static String all(InputStream input)throws IOException {return new String(input.readAllBytes(),StandardCharsets.US_ASCII);}
    static class Factory extends SocketFactory {
        volatile int target;
        final List<Integer> ports=Collections.synchronizedList(new ArrayList<>());
        final AtomicInteger connections=new AtomicInteger();
        Factory(int port){target=port;}
        public Socket createSocket(){return new Socket(){public void connect(SocketAddress endpoint,int timeout)throws IOException {
            InetSocketAddress destination=(InetSocketAddress)endpoint;
            check(!destination.isUnresolved()&&destination.getAddress().equals(LOCAL),"Network-scoped resolver supplied the address");
            check(timeout==10000,"Connect timeout is bounded"); ports.add(destination.getPort());connections.incrementAndGet();
            super.connect(new InetSocketAddress(LOCAL,target),timeout);
        }};}
        public Socket createSocket(String h,int p)throws IOException {throw new AssertionError("Default DNS factory overload is forbidden");}
        public Socket createSocket(InetAddress h,int p)throws IOException {throw new AssertionError("Only tracked unconnected sockets are accepted");}
        public Socket createSocket(String h,int p,InetAddress l,int lp)throws IOException {throw new AssertionError();}
        public Socket createSocket(InetAddress h,int p,InetAddress l,int lp)throws IOException {throw new AssertionError();}
    }
    static class Fixture implements AutoCloseable {
        final ServerSocket server;
        final ExecutorService worker=Executors.newSingleThreadExecutor();
        Future<String> received;
        Fixture()throws IOException{this(null);}
        Fixture(SSLContext tls)throws IOException{server=tls==null?new ServerSocket(0,8,LOCAL):tls.getServerSocketFactory().createServerSocket(0,8,LOCAL);}
        void http(String response) {received=worker.submit(()->{try(Socket client=server.accept()){
            client.setSoTimeout(3000);String request=header(client.getInputStream());
            client.getOutputStream().write(response.getBytes(StandardCharsets.US_ASCII));return request;}});}
        void echo() {received=worker.submit(()->{try(Socket client=server.accept()){
            client.setSoTimeout(3000);byte[] bytes=client.getInputStream().readNBytes(4);
            client.getOutputStream().write(bytes);return new String(bytes,StandardCharsets.US_ASCII);}});}
        public void close()throws IOException {server.close();worker.shutdownNow();}
    }
    static URI address(Z8SetupDownloadProxy proxy)throws Exception {return new URI(proxy.environment().get("http_proxy"));}
    static String auth(Z8SetupDownloadProxy proxy)throws Exception {
        return "Proxy-Authorization: Basic "+Base64.getEncoder().encodeToString(address(proxy).getRawUserInfo().getBytes(StandardCharsets.US_ASCII))+"\r\n";
    }
    static Socket client(Z8SetupDownloadProxy proxy)throws Exception {Socket s=new Socket(LOCAL,address(proxy).getPort());s.setSoTimeout(4000);return s;}
    static String request(Z8SetupDownloadProxy proxy,String first,String extra,boolean authenticate)throws Exception {
        try(Socket socket=client(proxy)) {socket.getOutputStream().write((first+"\r\n"+(authenticate?auth(proxy):"")+extra+"\r\n").getBytes(StandardCharsets.US_ASCII));
            return all(socket.getInputStream());}
    }
    static void deny(Z8SetupDownloadProxy proxy,Factory factory,String first,String extra,String status)throws Exception {
        int before=factory.connections.get();check(request(proxy,first,extra,true).startsWith("HTTP/1.1 "+status),"Denied "+first);
        check(factory.connections.get()==before,"Rejected request never creates upstream socket");
    }
    static SSLContext serverContext(String path)throws Exception {
        KeyStore keys=KeyStore.getInstance("PKCS12");
        try(InputStream input=new FileInputStream(path)){keys.load(input,"fixturepass".toCharArray());}
        KeyManagerFactory managers=KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm());
        managers.init(keys,"fixturepass".toCharArray());
        SSLContext context=SSLContext.getInstance("TLS");context.init(managers.getKeyManagers(),null,null);return context;
    }
    public static void main(String[]args)throws Exception {
        SSLContext trusted=serverContext(args[0]), untrusted=serverContext(args[1]);
        try(Fixture fixture=new Fixture(trusted); Fixture tunnel=new Fixture()) {
            Factory factory=new Factory(fixture.server.getLocalPort());
            List<String> resolved=Collections.synchronizedList(new ArrayList<>());
            try(Z8SetupDownloadProxy proxy=new Z8SetupDownloadProxy(factory,host->{resolved.add(host);return new InetAddress[]{LOCAL};})) {
                check(address(proxy).getHost().equals("127.0.0.1"),"Proxy listens only on loopback");
                check(proxy.environment().get("https_proxy").equals(proxy.environment().get("http_proxy")),"HTTPS uses authenticated HTTP CONNECT proxy");
                check(proxy.environment().get("no_proxy").isEmpty()&&proxy.environment().get("NO_PROXY").isEmpty(),"No inherited bypass list");
                check(request(proxy,"GET http://ports.ubuntu.com/ HTTP/1.1","",false).startsWith("HTTP/1.1 407"),"Missing authentication refused");
                check(request(proxy,"GET http://ports.ubuntu.com/ HTTP/1.1","Proxy-Authorization: Basic wrong\r\n",false).startsWith("HTTP/1.1 407"),"Wrong authentication refused");
                check(factory.connections.get()==0&&resolved.isEmpty(),"Unauthenticated client performs no DNS or connection");

                fixture.http("HTTP/1.1 200 OK\r\nContent-Length: 7\r\nConnection: close\r\n\r\nfixture");
                String response=request(proxy,"GET http://ports.ubuntu.com/ubuntu-ports/file?version=1 HTTP/1.1",
                    "Host: attacker.invalid\r\nConnection: keep-alive, x-private\r\nX-Private: removed\r\nRange: bytes=0-6\r\n",true);
                check(response.endsWith("fixture"),"HTTP response streamed from injected bound socket");
                String sent=fixture.received.get(3,TimeUnit.SECONDS);
                check(sent.startsWith("GET /ubuntu-ports/file?version=1 HTTP/1.1\r\nHost: ports.ubuntu.com\r\n"),"Absolute-form URL becomes origin-form and correct Host");
                check(!sent.toLowerCase(Locale.ROOT).contains("proxy-authorization")&&!sent.contains("removed")&&!sent.contains("attacker.invalid"),"Proxy credentials and hop headers never reach origin");
                check(sent.contains("range: bytes=0-6"),"APT range requests preserved");
                check(resolved.equals(List.of("ports.ubuntu.com"))&&factory.ports.equals(List.of(443)),"APT HTTP is upgraded to TLS on the selected network");

                fixture.http("HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n");
                check(request(proxy,"HEAD http://archive.ubuntu.com/ubuntu/ HTTP/1.0","",true).startsWith("HTTP/1.1 200"),"Legacy Ubuntu HEAD supported over TLS");
                check(fixture.received.get(3,TimeUnit.SECONDS).startsWith("HEAD /ubuntu/ HTTP/1.1"),"HEAD forwarded correctly");

                for(String path:List.of("/debian/dists/trixie/InRelease","/debian-security/dists/trixie-security/InRelease")) {
                    fixture.http("HTTP/1.1 200 OK\r\nContent-Length: 6\r\n\r\ndebian");
                    check(request(proxy,"GET http://deb.debian.org"+path+" HTTP/1.1","",true).endsWith("debian"),"Both exact Debian archive paths work without guest CA certificates");
                    check(fixture.received.get(3,TimeUnit.SECONDS).startsWith("GET "+path+" HTTP/1.1\r\nHost: deb.debian.org\r\n"),"Debian origin path preserved");
                }
                fixture.http("HTTP/1.1 302 Found\r\nLocation: http://deb.debian.org/debian/next\r\nContent-Length: 0\r\n\r\n");
                int beforeRedirect=factory.connections.get();
                check(request(proxy,"GET http://deb.debian.org/debian/redirect HTTP/1.1","",true).startsWith("HTTP/1.1 302"),"Redirect returned without automatic follow");
                fixture.received.get(3,TimeUnit.SECONDS);
                check(factory.connections.get()==beforeRedirect+1,"Proxy does not follow redirect to a new connection");
                fixture.http("HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n");
                check(request(proxy,"GET http://deb.debian.org/debian/next HTTP/1.1","",true).startsWith("HTTP/1.1 200"),"Follow-up HTTP request is upgraded again");
                fixture.received.get(3,TimeUnit.SECONDS);
                check(factory.ports.stream().allMatch(port->port==443),"No off-device HTTP or redirect downgrade");

                for(String host:new String[]{"nodejs.org","api.github.com","github.com","release-assets.githubusercontent.com","objects.githubusercontent.com","downloads.claude.ai"}) {
                factory.target=tunnel.server.getLocalPort();tunnel.echo();
                try(Socket socket=client(proxy)) {
                    socket.getOutputStream().write(("CONNECT "+host+":443 HTTP/1.1\r\n"+auth(proxy)+"\r\n").getBytes(StandardCharsets.US_ASCII));
                    check(header(socket.getInputStream()).startsWith("HTTP/1.1 200 Connection Established"),"Authenticated CONNECT established");
                    socket.getOutputStream().write("PING".getBytes(StandardCharsets.US_ASCII));
                    check(new String(socket.getInputStream().readNBytes(4),StandardCharsets.US_ASCII).equals("PING"),"CONNECT relays both directions");
                }
                check(tunnel.received.get(3,TimeUnit.SECONDS).equals("PING")&&factory.ports.get(factory.ports.size()-1)==443,"CONNECT tunnel remains byte-transparent on port 443");
                }

                deny(proxy,factory,"GET http://example.com/ HTTP/1.1","","403");
                deny(proxy,factory,"GET http://ports.ubuntu.com.evil/ HTTP/1.1","","403");
                deny(proxy,factory,"GET http://deb.debian.org.evil/debian/ HTTP/1.1","","403");
                deny(proxy,factory,"GET http://deb.debian.org/unrelated/ HTTP/1.1","","403");
                deny(proxy,factory,"GET http://deb.debian.org/debian/../private HTTP/1.1","","403");
                deny(proxy,factory,"GET http://deb.debian.org/debian/%2e%2e/private HTTP/1.1","","403");
                deny(proxy,factory,"GET http://nodejs.org/ HTTP/1.1","","403");
                deny(proxy,factory,"GET http://ports.ubuntu.com:8080/ HTTP/1.1","","403");
                deny(proxy,factory,"GET http://user@ports.ubuntu.com/ HTTP/1.1","","403");
                deny(proxy,factory,"GET https://nodejs.org/ HTTP/1.1","","403");
                deny(proxy,factory,"CONNECT nodejs.org:80 HTTP/1.1","","403");
                deny(proxy,factory,"CONNECT nodejs.org:443/extra HTTP/1.1","","403");
                deny(proxy,factory,"CONNECT 127.0.0.1:443 HTTP/1.1","","403");
                deny(proxy,factory,"CONNECT api.github.com.evil:443 HTTP/1.1","","403");
                deny(proxy,factory,"CONNECT raw.githubusercontent.com:443 HTTP/1.1","","403");
                deny(proxy,factory,"GET http://downloads.claude.ai/ HTTP/1.1","","403");
                deny(proxy,factory,"POST http://ports.ubuntu.com/ HTTP/1.1","","405");
                deny(proxy,factory,"GET http://ports.ubuntu.com/ubuntu-ports/ HTTP/1.1","Content-Length: 1\r\n","400");
                deny(proxy,factory,"GET http://ports.ubuntu.com/ubuntu-ports/ HTTP/1.1","Transfer-Encoding: chunked\r\n","400");
                deny(proxy,factory,"GET http://ports.ubuntu.com/ HTTP/1.1","Host: one\r\nhost: two\r\n","400");
                deny(proxy,factory,"GET http://ports.ubuntu.com/ HTTP/1.1"," Bad: folded\r\n","400");
                int beforeLimit=factory.connections.get();
                try {check(request(proxy,"GET http://ports.ubuntu.com/ HTTP/1.1","X-Long: "+"x".repeat(17000)+"\r\n",true).startsWith("HTTP/1.1 400"),"Oversized headers refused");}
                catch(SocketException reset){checks++; /* Closing with unread oversized input can reset TCP. */}
                check(factory.connections.get()==beforeLimit,"Oversized header never creates an upstream socket");

                List<Socket> waiting=new ArrayList<>();
                for(int i=0;i<8;i++){waiting.add(client(proxy));Thread.sleep(20);}
                try(Socket ninth=client(proxy)){check(ninth.getInputStream().read()==-1,"Ninth pending client is immediately closed");}
                proxy.close();proxy.close();
                for(Socket socket:waiting){check(socket.getInputStream().read()==-1,"Close cancels pending header reads");socket.close();}
                try {client(proxy);throw new AssertionError("Closed listener accepted a client");}catch(ConnectException expected){checks++;}
            }
        }
        // Real TLS must reject a trusted certificate for another hostname and
        // an untrusted certificate even when its hostname matches.
        for(boolean wrongHost:List.of(true,false)) {
            try(Fixture fixture=new Fixture(wrongHost?trusted:untrusted)) {
                Factory factory=new Factory(fixture.server.getLocalPort());
                try(Z8SetupDownloadProxy proxy=new Z8SetupDownloadProxy(factory,host->new InetAddress[]{LOCAL})) {
                    fixture.http("HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n");
                    String host=wrongHost?"security.ubuntu.com/ubuntu/":"deb.debian.org/debian/";
                    check(request(proxy,"GET http://"+host+" HTTP/1.1","",true).startsWith("HTTP/1.1 502"),"Invalid TLS identity or trust is refused");
                    try{fixture.received.get(3,TimeUnit.SECONDS);throw new AssertionError("Invalid TLS accepted HTTP bytes");}
                    catch(ExecutionException expected){checks++;}
                    check(factory.ports.equals(List.of(443)),"Failed TLS never retries over HTTP");
                }
            }
        }
        // Network-policy closure must also cancel an upgraded TLS request, not
        // leave its Android-bound transport alive until the read timeout.
        try(Fixture fixture=new Fixture(trusted)) {
            Factory factory=new Factory(fixture.server.getLocalPort());
            Z8SetupDownloadProxy proxy=new Z8SetupDownloadProxy(factory,host->new InetAddress[]{LOCAL});
            CountDownLatch accepted=new CountDownLatch(1);
            fixture.received=fixture.worker.submit(()->{try(Socket peer=fixture.server.accept()){
                peer.setSoTimeout(4000);header(peer.getInputStream());accepted.countDown();
                return Integer.toString(peer.getInputStream().read());}});
            try(Socket socket=client(proxy)) {
                socket.getOutputStream().write(("GET http://deb.debian.org/debian/pending HTTP/1.1\r\n"+auth(proxy)+"\r\n").getBytes(StandardCharsets.US_ASCII));
                check(accepted.await(3,TimeUnit.SECONDS),"Upgraded TLS request reaches fixture before cancellation");
                proxy.close();
                check(socket.getInputStream().read()==-1&&fixture.received.get(3,TimeUnit.SECONDS).equals("-1"),"Closure terminates upgraded TLS and local APT endpoints");
            } finally {proxy.close();}
        }
        // Closing a proxy also disconnects an established upstream tunnel.
        try(Fixture fixture=new Fixture()) {
            Factory factory=new Factory(fixture.server.getLocalPort());
            Z8SetupDownloadProxy proxy=new Z8SetupDownloadProxy(factory,host->new InetAddress[]{LOCAL});
            Future<Integer> ended=fixture.worker.submit(()->{try(Socket peer=fixture.server.accept()){peer.setSoTimeout(4000);return peer.getInputStream().read();}});
            try(Socket socket=client(proxy)) {
                socket.getOutputStream().write(("CONNECT nodejs.org:443 HTTP/1.1\r\n"+auth(proxy)+"\r\n").getBytes(StandardCharsets.US_ASCII));
                header(socket.getInputStream());proxy.close();
                check(socket.getInputStream().read()==-1&&ended.get(3,TimeUnit.SECONDS)==-1,"Network policy closure terminates both tunnel endpoints");
            } finally {proxy.close();}
        }
        // A selected-network failure must never fall back to the default socket factory.
        AtomicInteger failedFactory=new AtomicInteger();
        SocketFactory fail=new Factory(1){public Socket createSocket()throws RuntimeException{failedFactory.incrementAndGet();throw new IllegalStateException("Selected network lost");}};
        try(Z8SetupDownloadProxy proxy=new Z8SetupDownloadProxy(fail,host->new InetAddress[]{LOCAL})) {
            check(request(proxy,"GET http://security.ubuntu.com/ubuntu/ HTTP/1.1","",true).startsWith("HTTP/1.1 502"),"Selected network loss returns failure");
            check(failedFactory.get()==1,"No fallback connection is attempted");
        }
        try {Z8SetupDownloadProxy.open(new android.content.Context(),null);throw new AssertionError("Null network allowed");}
        catch(IOException expected){checks++;}
        System.out.println("PASS: installer proxy ("+checks+" checks)");
    }
}
'''


if __name__ == '__main__':
    unittest.main()
