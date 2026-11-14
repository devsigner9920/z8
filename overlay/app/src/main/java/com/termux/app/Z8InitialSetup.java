package com.termux.app;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;
import java.io.IOException;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

/** Explicit local preparation of the embedded terminal; optional downloads live in Tools. */
public final class Z8InitialSetup {
    public static final String NOTIFICATION_ID = "__initial_setup__";
    private static final String PREFS = "z8.initial-setup";
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    // A replacement service cannot overlap an old preparation process cleanup.
    private static final ExecutorService WORKER = Executors.newSingleThreadExecutor();
    private static final Set<Runnable> LISTENERS = new LinkedHashSet<>();
    private static volatile Job active;
    private static volatile State latest;
    // WAITING_NETWORK is retained for old interrupted journals; it now means Resume.
    public enum Phase { CONSENT, RUNNING, WAITING_NETWORK, FAILED, READY }
    public static final class State {
        public final Phase phase;
        public final String stage, message;
        public final int percent;
        public final boolean allowMetered;
        State(Phase phase, String stage, int percent, String message, boolean allowMetered) {
            this.phase=phase; this.stage=stage; this.percent=percent; this.message=message; this.allowMetered=false;
        }
    }
    private static final class Job {
        final TermuxService service;
        final String id=UUID.randomUUID().toString();
        final AtomicBoolean scheduled=new AtomicBoolean();
        volatile Thread thread;
        volatile boolean abandoned;
        volatile State progress=new State(Phase.RUNNING,"bootstrap",-1,
            Z8Text.text("Preparing the local terminal", "로컬 터미널 준비"),false);
        Job(TermuxService service) { this.service=service; }
    }
    private Z8InitialSetup() {}
    private static void mainThread() {
        if (Looper.myLooper()!=Looper.getMainLooper()) throw new IllegalStateException("Setup ownership stays on main thread");
    }
    private static SharedPreferences preferences(Context context) { return context.getSharedPreferences(PREFS,Context.MODE_PRIVATE); }
    public static boolean hasConsent(Context context) { return preferences(context).getBoolean("consent",false); }
    public static boolean isReady(Context context) {
        return "ready".equals(preferences(context).getString("status","")) && Z8EnvironmentTemplate.isReady(context);
    }
    public static State state(Context context) {
        if (isReady(context)) return new State(Phase.READY,"ready",100,Z8Text.text("Terminal ready","터미널 준비 완료"),false);
        Job job=active;
        if (job!=null && !job.abandoned) return job.progress;
        if (latest!=null && latest.phase!=Phase.READY) return latest;
        String status=preferences(context).getString("status","");
        if ("failed".equals(status)) return new State(Phase.FAILED,"error",-1,
            Z8Text.text("Retry local preparation. Your project files are preserved.","로컬 준비를 다시 시도해 주세요. 프로젝트 파일은 보존됩니다."),false);
        if ("running".equals(status)||"waiting".equals(status)) return new State(Phase.WAITING_NETWORK,"bootstrap",-1,
            Z8Text.text("Continue preparing the embedded terminal. No internet connection is needed.","내장 터미널 준비를 이어갑니다. 인터넷 연결은 필요하지 않습니다."),false);
        return new State(Phase.CONSENT,"",-1,"",false);
    }
    public static void addListener(Runnable listener) { mainThread(); LISTENERS.add(listener); }
    public static void removeListener(Runnable listener) { mainThread(); LISTENERS.remove(listener); }
    private static void changed() { for(Runnable listener:new LinkedHashSet<>(LISTENERS)) listener.run(); }
    public static boolean hasWork(TermuxService service) { Job job=active; return job!=null&&job.service==service&&!job.abandoned; }
    public static void request(TermuxService service,boolean unusedAllowMetered) {
        mainThread();
        if(isReady(service)||active!=null||service.wantsToStop()||service.z8IsStopRequested()) return;
        if(!preferences(service).edit().putBoolean("consent",true).putBoolean("allowMetered",false)
                .putString("status","running").putString("stage","bootstrap").commit()) {
            latest=new State(Phase.FAILED,"error",-1,Z8Text.text("Could not save setup progress. Check available storage.","준비 상태를 저장하지 못했습니다. 저장 공간을 확인해 주세요."),false);
            changed(); return;
        }
        start(service);
    }
    /** Only accepted local preparation resumes; never a package install or CLI action. */
    public static void resume(TermuxService service) {
        mainThread();
        if(!hasConsent(service)||isReady(service)||active!=null||service.wantsToStop()||service.z8IsStopRequested()) return;
        String status=preferences(service).getString("status","");
        if(!"running".equals(status)&&!"waiting".equals(status)) return;
        if(Z8EnvironmentTemplate.isReady(service)) {
            if(preferences(service).edit().putString("status","ready").putString("stage","ready").commit()) { latest=null; changed(); }
            return;
        }
        start(service);
    }
    private static void start(TermuxService service) {
        Job job=new Job(service); active=job; latest=null;
        try {
            Z8PreparationNotification.begin(service,job.id,NOTIFICATION_ID,"z8");
            Z8PreparationService.begin(service,job.id,()->WORKER.execute(()->run(job)),message->interrupted(job,message));
        } catch(RuntimeException failure) {
            finish(job,new IOException(Z8Text.text("Could not start foreground preparation. Reopen Z8 and retry.","백그라운드 준비를 시작하지 못했습니다. Z8를 다시 열고 시도해 주세요."),failure)); return;
        }
        changed();
    }
    private static void run(Job job) {
        job.thread=Thread.currentThread(); Exception failure=null;
        try {
            if(job.abandoned) throw new InterruptedException();
            final String[] stage={""};
            Z8ProjectPreparation.run(job.service.getApplicationContext(),Z8EnvironmentTemplate.ID,(name,percent,message)->{
                if(job.abandoned||Thread.currentThread().isInterrupted()) throw new java.util.concurrent.CancellationException("Local preparation paused");
                if(!name.equals(stage[0])) {
                    if(!preferences(job.service).edit().putString("status","running").putString("stage",name).commit())
                        throw new IllegalStateException(Z8Text.text("Could not save preparation status.","준비 상태를 저장하지 못했습니다."));
                    stage[0]=name;
                }
                job.progress=new State(Phase.RUNNING,name,percent,message,false);
                Z8PreparationNotification.progress(job.service,job.id,name,percent,message);
                if(job.scheduled.compareAndSet(false,true)) MAIN.postDelayed(()->{job.scheduled.set(false);if(active==job)changed();},250);
            },Collections.emptyMap());
            if(job.abandoned||Thread.currentThread().isInterrupted()) throw new InterruptedException();
            if(!Z8EnvironmentTemplate.isReady(job.service)) throw new IOException(Z8Text.text("Could not verify the local terminal.","로컬 터미널을 확인하지 못했습니다."));
            if(!preferences(job.service).edit().putString("status","ready").putString("stage","ready").commit())
                throw new IOException(Z8Text.text("Could not save completed setup.","준비 완료 상태를 저장하지 못했습니다."));
        } catch(Exception error) { failure=error; }
        finally { job.thread=null; Thread.interrupted(); }
        Exception result=failure; MAIN.post(()->finish(job,result));
    }
    private static void finish(Job job,Exception error) {
        Z8PreparationService.finish(job.service,job.id);
        mainThread(); if(active!=job||job.abandoned)return;
        boolean success=error==null;
        if(!success)preferences(job.service).edit().putString("status","failed").commit();
        latest=new State(success?Phase.READY:Phase.FAILED,success?"ready":job.progress.stage,success?100:-1,
            success?Z8Text.text("Terminal ready","터미널 준비 완료"):error.getMessage()==null?Z8Text.text("Could not prepare the local terminal.","로컬 터미널을 준비하지 못했습니다."):error.getMessage(),false);
        active=null; Z8PreparationNotification.finish(job.service,job.id,success,null); job.service.updateNotification(); changed();
    }
    private static void interrupted(Job job,String message) {
        mainThread(); if(active!=job)return;
        job.abandoned=true; active=null;
        if(job.thread!=null)job.thread.interrupt();
        preferences(job.service).edit().putString("status","failed").commit();
        latest=new State(Phase.FAILED,"error",-1,message,false);
        Z8PreparationNotification.finish(job.service,job.id,false,null);
        job.service.updateNotification(); changed();
    }
    public static void stop(TermuxService service) {
        mainThread(); Job job=active; if(job==null||job.service!=service)return;
        job.abandoned=true; active=null; latest=null;
        if(job.thread!=null)job.thread.interrupt();
        Z8PreparationService.finish(service,job.id);
        Z8PreparationNotification.releaseOwner(service);
    }
}
