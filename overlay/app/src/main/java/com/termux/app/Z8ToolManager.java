package com.termux.app;

import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.ServiceConnection;
import android.content.SharedPreferences;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import java.io.IOException;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

/** Explicit selected-tool operations owned by the foreground execution service. */
public final class Z8ToolManager {
    private static final Handler MAIN=new Handler(Looper.getMainLooper());
    // A single queue is intentionally stronger than per-project serialization.
    // A replacement service cannot race cleanup from an interrupted installer.
    private static final ExecutorService WORKER=Executors.newSingleThreadExecutor();
    private static final ConcurrentHashMap<String,Job> JOBS=new ConcurrentHashMap<>();
    private static final ConcurrentHashMap<String,State> STATES=new ConcurrentHashMap<>();
    private static final Set<Runnable> LISTENERS=new LinkedHashSet<>();
    public enum Phase { IDLE, QUEUED, RUNNING, WAITING_NETWORK, FAILED, READY }
    public static final class State {
        public final Phase phase;
        public final String toolId,version,stage,message;
        public final boolean update,allowMetered;
        public final int percent;
        State(Phase phase,String toolId,boolean update,String version,String stage,int percent,String message,boolean allowMetered) {
            this.phase=phase;this.toolId=toolId;this.update=update;this.version=version;this.stage=stage;
            this.percent=percent;this.message=message;this.allowMetered=allowMetered;
        }
        public boolean busy(){return phase==Phase.QUEUED||phase==Phase.RUNNING;}
    }
    private static final class Job implements ServiceConnection {
        final Context context; final String projectId,toolId,version,id=UUID.randomUUID().toString();
        final boolean update,allowMetered;
        final AtomicBoolean scheduled=new AtomicBoolean();
        volatile TermuxService service;
        volatile Thread thread;
        volatile Z8SetupDownloadProxy proxy;
        volatile boolean abandoned,networkStopped,enqueued;
        boolean bound,registered;
        Network network; ConnectivityManager connectivity;
        final ConnectivityManager.NetworkCallback callback=new ConnectivityManager.NetworkCallback(){
            @Override public void onAvailable(Network n){if(!network.equals(n))pause(Job.this);}
            @Override public void onLost(Network n){if(network.equals(n))pause(Job.this);}
            @Override public void onCapabilitiesChanged(Network n,NetworkCapabilities caps){if(network.equals(n)&&!allowed(caps,allowMetered))pause(Job.this);}
        };
        Job(Context context,String projectId,String toolId,boolean update,String version,boolean allowMetered){
            this.context=context;this.projectId=projectId;this.toolId=toolId;this.update=update;this.version=version;this.allowMetered=allowMetered;
        }
        @Override public void onServiceConnected(ComponentName name,IBinder binder){connected(this,((TermuxService.LocalBinder)binder).service);}
        @Override public void onServiceDisconnected(ComponentName name){
            if(JOBS.get(projectId)!=this){release(this);return;}
            abandoned=true;pause(this);
            save(this,Phase.FAILED,"The runtime stopped. Retry to validate completed steps.");
            if(!enqueued)JOBS.remove(projectId,this);
            publish(this,Phase.FAILED,"error",-1,Z8Text.text("The runtime stopped. Retry to validate completed steps.","실행 서비스가 중단되었습니다. 다시 시도하면 완료된 단계를 확인합니다."));
            release(this);
        }
        @Override public void onBindingDied(ComponentName name){onServiceDisconnected(name);}
        @Override public void onNullBinding(ComponentName name){onServiceDisconnected(name);}
    }
    private Z8ToolManager(){}
    private static void mainThread(){if(Looper.myLooper()!=Looper.getMainLooper())throw new IllegalStateException("Tool actions stay on the main thread");}
    public static boolean validTool(String tool){return Arrays.asList("python","git","node","codex","claude","gh","ssh","build-tools","tmux","utilities").contains(tool);}
    private static boolean validProject(String id){try{return id!=null&&UUID.fromString(id).toString().equals(id)&&!Z8EnvironmentTemplate.isTemplate(id);}catch(IllegalArgumentException e){return false;}}
    private static void validate(String tool,boolean update,String version){
        new Z8ToolCatalog.Request(tool,update,version);
    }
    static String[] command(String tool,boolean update,String version){
        validate(tool,update,version);
        String[] prefix={"/bin/bash","/usr/local/lib/z8/tool-manager.sh",update?"--update":"--apply",tool};
        if(version==null||version.isEmpty())return prefix;
        return new String[]{prefix[0],prefix[1],prefix[2],prefix[3],"--version",version};
    }
    static boolean validCommand(String[] command){
        if(command==null||(command.length!=4&&command.length!=6)||!"/bin/bash".equals(command[0])
            ||!"/usr/local/lib/z8/tool-manager.sh".equals(command[1])||!("--apply".equals(command[2])||"--update".equals(command[2])))return false;
        try{if(command.length==6&&(!"--version".equals(command[4])||command[5]==null||command[5].isEmpty()))return false;
            validate(command[3],"--update".equals(command[2]),command.length==6?command[5]:null);return true;}catch(IllegalArgumentException e){return false;}
    }
    private static SharedPreferences prefs(Context context,String id){return context.getSharedPreferences("z8.tool-operation."+id,Context.MODE_PRIVATE);}
    public static State state(Context context,String projectId){
        if(!validProject(projectId))return new State(Phase.IDLE,"",false,"","",-1,"",false);
        State current=STATES.get(projectId);if(current!=null)return current;
        SharedPreferences p=prefs(context,projectId);String tool=p.getString("tool","");
        if(!validTool(tool))return new State(Phase.IDLE,"",false,"","",-1,"",false);
        String saved=p.getString("phase","");Phase phase;
        try{phase=Phase.valueOf(saved);}catch(IllegalArgumentException e){phase=Phase.FAILED;}
        boolean interrupted=phase==Phase.QUEUED||phase==Phase.RUNNING;
        return new State(interrupted?Phase.FAILED:phase,tool,p.getBoolean("update",false),p.getString("version",""),"",-1,
            interrupted?Z8Text.text("Installation was interrupted. Retry to validate completed steps.","설치가 중단되었습니다. 다시 시도하면 완료된 단계를 확인합니다."):p.getString("message",""),p.getBoolean("metered",false));
    }
    public static void addListener(Runnable listener){mainThread();LISTENERS.add(listener);}
    public static void removeListener(Runnable listener){mainThread();LISTENERS.remove(listener);}
    private static void changed(){for(Runnable listener:new LinkedHashSet<>(LISTENERS))listener.run();}
    public static boolean hasWork(TermuxService service){for(Job job:JOBS.values())if(job.service==service&&!job.abandoned)return true;return false;}
    public static boolean busy(String projectId){return projectId!=null&&JOBS.containsKey(projectId);}
    public static void start(Context context,String projectId,String toolId,boolean update,String version,boolean allowMetered){
        mainThread();validate(toolId,update,version);if(!validProject(projectId))throw new IllegalArgumentException("Invalid project");
        if(busy(projectId))return;
        Context app=context.getApplicationContext();Job job=new Job(app,projectId,toolId,update,version==null?"":version,allowMetered);
        if(Z8ProjectRemoval.isDeleting(projectId)){publish(job,Phase.FAILED,"error",-1,Z8Text.text("Wait for project deletion to finish.","프로젝트 삭제가 끝날 때까지 기다려 주세요."));return;}
        if(!save(job,Phase.QUEUED,"")){publish(job,Phase.FAILED,"error",-1,Z8Text.text("Could not save the requested operation.","요청한 작업을 저장하지 못했습니다."));return;}
        JOBS.put(projectId,job);publish(job,Phase.QUEUED,"queued",-1,Z8Text.text("Waiting to install the selected tool", "선택한 도구 설치 대기"));
        try{job.bound=app.bindService(new Intent(app,TermuxService.class),job,Context.BIND_AUTO_CREATE);
            if(!job.bound)finish(job,new IOException("Could not connect to the runtime service"));}
        catch(RuntimeException failure){finish(job,failure);}
    }
    private static void connected(Job job,TermuxService service){
        mainThread();if(job.abandoned||JOBS.get(job.projectId)!=job){release(job);return;}job.service=service;
        if(service.wantsToStop()||service.z8IsStopRequested()||Z8ProjectRemoval.isDeleting(job.projectId)){
            finish(job,new IOException(Z8Text.text("The runtime is stopping. Retry after it closes.","실행 환경 종료 중입니다. 종료 후 다시 시도해 주세요.")));return;}
        job.connectivity=service.getSystemService(ConnectivityManager.class);
        job.network=allowedNetwork(job.connectivity,job.allowMetered);
        if(job.network==null){job.networkStopped=true;finish(job,new IOException("Network consent required"));return;}
        try{service.z8AcquireExecution();Z8PreparationNotification.beginTool(service,job.id,job.projectId,Z8ToolCatalog.get(job.toolId).name(),job.update);
            job.connectivity.registerDefaultNetworkCallback(job.callback);job.registered=true;}
        catch(RuntimeException failure){finish(job,new IOException("Could not start foreground installation or monitor the selected connection",failure));return;}
        job.enqueued=true;WORKER.execute(()->run(job));
    }
    private static boolean allowed(NetworkCapabilities caps,boolean metered){return caps!=null&&caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
        &&caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)&&(metered||caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED));}
    private static Network allowedNetwork(ConnectivityManager manager,boolean metered){try{Network n=manager==null?null:manager.getActiveNetwork();return n!=null&&allowed(manager.getNetworkCapabilities(n),metered)&&n.equals(manager.getActiveNetwork())?n:null;}catch(SecurityException e){return null;}}
    private static void pause(Job job){job.networkStopped=true;Z8SetupDownloadProxy proxy=job.proxy;if(proxy!=null)proxy.close();Thread thread=job.thread;if(thread!=null)thread.interrupt();}
    private static void check(Job job)throws InterruptedException{
        if(job.abandoned||job.networkStopped||Thread.currentThread().isInterrupted())throw new InterruptedException();
        if(!job.network.equals(allowedNetwork(job.connectivity,job.allowMetered))){pause(job);throw new InterruptedException();}
    }
    private static void run(Job job){
        job.thread=Thread.currentThread();Exception failure=null;
        try{
            check(job);new Z8Projects(job.context).open(job.projectId);
            job.proxy=Z8SetupDownloadProxy.open(job.service,job.network);check(job);
            Z8ProjectPreparation.installTool(job.context,job.projectId,job.toolId,job.update,job.version,(stage,percent,message)->{
                if(job.abandoned||job.networkStopped||Thread.currentThread().isInterrupted())throw new java.util.concurrent.CancellationException("Tool operation paused");
                STATES.put(job.projectId,new State(Phase.RUNNING,job.toolId,job.update,job.version,stage,percent,message,job.allowMetered));
                Z8PreparationNotification.progress(job.service,job.id,stage,percent,message);
                if(job.scheduled.compareAndSet(false,true))MAIN.postDelayed(()->{job.scheduled.set(false);if(JOBS.get(job.projectId)==job)changed();},250);
            },job.proxy.environment());
            // A completed verifier is valid even if the connection disappears afterwards.
            if(job.abandoned||Thread.currentThread().isInterrupted()&&!job.networkStopped)throw new InterruptedException();
        }catch(Exception error){failure=error;}
        finally{if(job.proxy!=null)job.proxy.close();job.thread=null;Thread.interrupted();}
        Exception result=failure;MAIN.post(()->finish(job,result));
    }
    private static boolean save(Job job,Phase phase,String message){return prefs(job.context,job.projectId).edit().putString("tool",job.toolId).putBoolean("update",job.update)
        .putString("version",job.version).putBoolean("metered",job.allowMetered).putString("phase",phase.name()).putString("message",message).commit();}
    private static void publish(Job job,Phase phase,String stage,int percent,String message){
        STATES.put(job.projectId,new State(phase,job.toolId,job.update,job.version,stage,percent,message,job.allowMetered));changed();
    }
    private static void finish(Job job,Exception error){
        mainThread();unregister(job);
        if(JOBS.get(job.projectId)!=job){release(job);return;}
        if(job.abandoned){JOBS.remove(job.projectId,job);STATES.remove(job.projectId);release(job);changed();return;}
        boolean success=error==null;Phase phase=success?Phase.READY:job.networkStopped?Phase.WAITING_NETWORK:Phase.FAILED;
        String message=success?Z8Text.text("Selected tool ready", "선택한 도구 준비 완료"):job.networkStopped?
            Z8Text.text("Use an unmetered connection or allow this metered network, then retry. Completed steps are preserved.","데이터 제한이 없는 연결을 사용하거나 이 유료 네트워크를 허용한 후 다시 시도해 주세요. 완료된 단계는 보존됩니다."):
            error.getMessage()==null?Z8Text.text("Installation did not finish. Retry after checking the error.","설치가 완료되지 않았습니다. 오류를 확인하고 다시 시도해 주세요."):error.getMessage();
        if(!save(job,phase,message)){phase=Phase.FAILED;message=Z8Text.text("Could not save the operation result. Check tool status before retrying.","작업 결과를 저장하지 못했습니다. 다시 시도하기 전에 도구 상태를 확인해 주세요.");success=false;}
        JOBS.remove(job.projectId,job);Z8Guest.invalidateReadiness(job.projectId);publish(job,phase,success?"ready":"error",success?100:-1,message);
        if(job.service!=null){
            if(phase==Phase.WAITING_NETWORK)Z8PreparationNotification.waiting(job.service,job.id);
            else Z8PreparationNotification.finish(job.service,job.id,success,null);
            job.service.updateNotification();}
        release(job);
    }
    private static void unregister(Job job){if(job.registered){try{job.connectivity.unregisterNetworkCallback(job.callback);}catch(IllegalArgumentException ignored){}job.registered=false;}}
    private static void release(Job job){unregister(job);if(job.bound){job.bound=false;try{job.context.unbindService(job);}catch(IllegalArgumentException ignored){}}}
    public static void stop(TermuxService service){
        mainThread();for(Job job:JOBS.values())if(job.service==service){job.abandoned=true;pause(job);if(!job.enqueued)JOBS.remove(job.projectId,job);
            save(job,Phase.FAILED,Z8Text.text("Installation stopped. Retry to validate completed steps.","설치가 중단되었습니다. 다시 시도하면 완료된 단계를 확인합니다."));STATES.remove(job.projectId);release(job);}
        changed();
    }
}
