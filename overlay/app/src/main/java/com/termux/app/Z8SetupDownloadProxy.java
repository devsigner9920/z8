package com.termux.app;

import android.content.Context;
import android.net.Network;

import java.io.ByteArrayOutputStream;
import java.io.BufferedInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicBoolean;
import javax.net.SocketFactory;

/** Short-lived authenticated proxy for managed installer downloads, never general browsing. */
public final class Z8SetupDownloadProxy implements AutoCloseable {
    interface Resolver { InetAddress[] resolve(String host) throws IOException; }
    private static final Set<String> HOSTS = Collections.unmodifiableSet(new HashSet<>(Arrays.asList(
        "ports.ubuntu.com", "archive.ubuntu.com", "security.ubuntu.com", "nodejs.org")));
    private static final Set<String> HOP_HEADERS = Collections.unmodifiableSet(new HashSet<>(Arrays.asList(
        "connection", "proxy-connection", "proxy-authorization", "proxy-authenticate", "keep-alive",
        "te", "trailer", "transfer-encoding", "upgrade", "host")));
    private static final int HEADER_LIMIT = 16384;
    private static final int CONNECT_TIMEOUT = 10000;
    private static final int IDLE_TIMEOUT = 60000;
    private final SocketFactory factory;
    private final Resolver resolver;
    private final ServerSocket server;
    private final Set<Socket> sockets = ConcurrentHashMap.newKeySet();
    private final Semaphore clients = new Semaphore(8);
    private final ExecutorService workers = Executors.newFixedThreadPool(16, task -> {
        Thread thread = new Thread(task, "z8-setup-download"); thread.setDaemon(true); return thread;
    });
    private final AtomicBoolean closed = new AtomicBoolean();
    private final byte[] authentication;
    private final Map<String, String> environment;

    public static Z8SetupDownloadProxy open(Context context, Network selected) throws IOException {
        if (selected == null) throw new IOException(Z8Text.text("No network is available for installation.", "설치에 사용할 네트워크가 없습니다."));
        // Both name resolution and sockets belong to the selected network. A lost
        // network fails instead of transparently falling back to mobile data.
        return new Z8SetupDownloadProxy(selected.getSocketFactory(), selected::getAllByName);
    }

    /** Injectable socket factory keeps host tests independent of Android and public internet. */
    Z8SetupDownloadProxy(SocketFactory factory, Resolver resolver) throws IOException {
        this.factory = factory; this.resolver = resolver;
        byte[] random = new byte[24]; new SecureRandom().nextBytes(random);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(random);
        authentication = ("Basic " + Base64.getEncoder().encodeToString(
            ("z8:" + token).getBytes(StandardCharsets.US_ASCII))).getBytes(StandardCharsets.US_ASCII);
        server = new ServerSocket();
        try { server.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 8); }
        catch (IOException error) { close(); throw error; }
        String url = "http://z8:" + token + "@127.0.0.1:" + server.getLocalPort();
        Map<String, String> variables = new LinkedHashMap<>();
        for (String name : Arrays.asList("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY")) variables.put(name, url);
        variables.put("no_proxy", ""); variables.put("NO_PROXY", "");
        environment = Collections.unmodifiableMap(variables);
        Thread acceptor = new Thread(this::accept, "z8-setup-proxy");
        acceptor.setDaemon(true); acceptor.start();
    }

    public Map<String, String> environment() { return environment; }

    private void accept() {
        while (!closed.get()) {
            Socket client = null;
            try {
                client = server.accept();
                if (!clients.tryAcquire()) { client.close(); continue; }
                Socket accepted = client;
                try {
                    track(accepted);
                    workers.execute(() -> { try { serve(accepted); }
                        finally { release(accepted); clients.release(); } });
                } catch (Exception stopped) { release(accepted); clients.release(); }
            } catch (IOException stopped) {
                if (client != null) release(client);
                if (!closed.get()) close();
            }
        }
    }

    private void serve(Socket client) {
        Socket upstream = null;
        boolean committed = false;
        try {
            client.setSoTimeout(15000);
            InputStream clientInput = new BufferedInputStream(client.getInputStream(), HEADER_LIMIT);
            Request request = read(clientInput);
            String supplied = request.headers.get("proxy-authorization");
            if (supplied == null || !MessageDigest.isEqual(authentication, supplied.getBytes(StandardCharsets.US_ASCII))) {
                reply(client, "407 Proxy Authentication Required", "Proxy-Authenticate: Basic realm=\"z8-setup\"\r\n"); return;
            }
            boolean tunnel = "CONNECT".equals(request.method);
            if (!tunnel && !"GET".equals(request.method) && !"HEAD".equals(request.method)) {
                reply(client, "405 Method Not Allowed", ""); return;
            }
            URI target;
            try { target = new URI(tunnel ? "https://" + request.target : request.target); }
            catch (Exception invalid) { reply(client, "400 Bad Request", ""); return; }
            String host = target.getHost();
            int port = target.getPort() == -1 ? (tunnel ? 443 : 80) : target.getPort();
            if (host == null || !HOSTS.contains(host.toLowerCase(Locale.ROOT)) || target.getRawUserInfo() != null
                    || target.getRawFragment() != null || request.target.indexOf('\\') >= 0
                    || !((tunnel && "https".equals(target.getScheme()) && port == 443
                        && (target.getRawPath() == null || target.getRawPath().isEmpty()) && target.getRawQuery() == null)
                    || (!tunnel && "http".equals(target.getScheme()) && port == 80))) {
                reply(client, "403 Forbidden", ""); return;
            }
            if (request.headers.containsKey("transfer-encoding")
                    || request.headers.containsKey("content-length") && !"0".equals(request.headers.get("content-length"))) {
                reply(client, "400 Bad Request", ""); return;
            }
            upstream = connect(host, port);
            client.setSoTimeout(IDLE_TIMEOUT);
            if (tunnel) {
                client.getOutputStream().write("HTTP/1.1 200 Connection Established\r\n\r\n".getBytes(StandardCharsets.US_ASCII));
                client.getOutputStream().flush(); committed = true;
                Socket destination = upstream;
                workers.execute(() -> {
                    try { copy(clientInput, destination.getOutputStream()); }
                    catch (IOException ignored) { /* Closing either endpoint cancels a stalled tunnel. */ }
                    finally { shutdownOutput(destination); }
                });
                copy(upstream.getInputStream(), client.getOutputStream());
            } else {
                String path = target.getRawPath();
                if (path == null || path.isEmpty()) path = "/";
                if (target.getRawQuery() != null) path += "?" + target.getRawQuery();
                StringBuilder headers = new StringBuilder(request.method + " " + path + " HTTP/1.1\r\nHost: " + host + "\r\nConnection: close\r\n");
                Set<String> omit = new HashSet<>(HOP_HEADERS);
                String connection = request.headers.get("connection");
                if (connection != null) for (String name : connection.split(",")) omit.add(name.trim().toLowerCase(Locale.ROOT));
                for (Map.Entry<String, String> header : request.headers.entrySet())
                    if (!omit.contains(header.getKey())) headers.append(header.getKey()).append(": ").append(header.getValue()).append("\r\n");
                headers.append("\r\n");
                upstream.getOutputStream().write(headers.toString().getBytes(StandardCharsets.US_ASCII));
                upstream.getOutputStream().flush(); committed = true;
                copy(upstream.getInputStream(), client.getOutputStream());
            }
        } catch (BadRequest invalid) {
            try { reply(client, "400 Bad Request", ""); } catch (IOException ignored) { }
        } catch (IOException | RuntimeException unavailable) {
            if (!committed && !closed.get()) try { reply(client, "502 Bad Gateway", ""); } catch (IOException ignored) { }
        } finally { if (upstream != null) release(upstream); }
    }

    private Socket connect(String host, int port) throws IOException {
        if (closed.get()) throw new IOException("Setup proxy closed");
        // DNS is explicitly scoped too; Socket.connect must never resolve via the
        // process default network. Addresses are already resolved below.
        InetAddress[] addresses = resolver.resolve(host);
        IOException last = new IOException("No installer server address");
        for (InetAddress address : addresses) {
            Socket socket = factory.createSocket();
            try {
                track(socket);
                socket.connect(new InetSocketAddress(address, port), CONNECT_TIMEOUT);
                socket.setSoTimeout(IDLE_TIMEOUT);
                if (closed.get()) throw new IOException("Setup proxy closed");
                return socket;
            } catch (IOException error) { last = error; release(socket); }
        }
        throw last;
    }

    private void track(Socket socket) throws IOException {
        sockets.add(socket);
        if (closed.get()) { release(socket); throw new IOException("Setup proxy closed"); }
    }
    private void release(Socket socket) { sockets.remove(socket); try { socket.close(); } catch (IOException ignored) { } }
    private static void shutdownOutput(Socket socket) { try { socket.shutdownOutput(); } catch (IOException ignored) { } }
    private static void copy(InputStream input, OutputStream output) throws IOException {
        byte[] buffer = new byte[16384]; int count;
        while ((count = input.read(buffer)) != -1) { output.write(buffer, 0, count); output.flush(); }
    }
    private static void reply(Socket client, String status, String extra) throws IOException {
        client.getOutputStream().write(("HTTP/1.1 " + status + "\r\nConnection: close\r\nContent-Length: 0\r\n" + extra + "\r\n").getBytes(StandardCharsets.US_ASCII));
        client.getOutputStream().flush();
    }

    private static final class BadRequest extends IOException { }
    private static final class Request {
        String method, target;
        final Map<String, String> headers = new LinkedHashMap<>();
    }
    private static Request read(InputStream input) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        int state = 0;
        while (state != 4) {
            int value = input.read();
            if (value == -1 || bytes.size() >= HEADER_LIMIT || value > 126 || value < 32 && value != '\r' && value != '\n' && value != '\t') throw new BadRequest();
            bytes.write(value);
            if (state == 0 || state == 2) state = value == '\r' ? state + 1 : 0;
            else state = value == '\n' ? state + 1 : value == '\r' ? 1 : 0;
        }
        String[] lines = bytes.toString(StandardCharsets.US_ASCII.name()).split("\r\n");
        String[] first = lines[0].split(" ", -1);
        if (first.length != 3 || !("HTTP/1.1".equals(first[2]) || "HTTP/1.0".equals(first[2]))) throw new BadRequest();
        Request request = new Request(); request.method = first[0]; request.target = first[1];
        for (int index = 1; index < lines.length; index++) {
            String line = lines[index]; int colon = line.indexOf(':');
            if (colon <= 0 || !line.substring(0, colon).matches("[!#$%&'*+.^_`|~0-9A-Za-z-]+")) throw new BadRequest();
            String name = line.substring(0, colon).toLowerCase(Locale.ROOT), value = line.substring(colon + 1).trim();
            if (value.indexOf('\r') >= 0 || value.indexOf('\n') >= 0 || request.headers.put(name, value) != null) throw new BadRequest();
        }
        return request;
    }

    @Override public void close() {
        if (!closed.compareAndSet(false, true)) return;
        try { server.close(); } catch (IOException ignored) { }
        for (Socket socket : sockets) release(socket);
        workers.shutdownNow();
    }
}
