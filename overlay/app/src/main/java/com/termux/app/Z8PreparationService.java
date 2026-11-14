package com.termux.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.ServiceConnection;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import android.os.Looper;
import com.termux.R;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Map;

/** Finite local preparation/download work. Interactive PTYs belong to TermuxService. */
public final class Z8PreparationService extends Service {
    public interface Interrupted { void stopped(String message); }
    private static final String REQUEST = "z8.preparation.request", STOP = "z8.preparation.STOP";
    private static final String CHANNEL = "z8_preparation_running";
    private static final int NOTIFICATION = 4210;
    // Main-thread-only. Unknown/restored intents never reconstruct or replay work.
    private static final Map<String, Lease> LEASES = new LinkedHashMap<>();
    private static Z8PreparationService running;
    private boolean ending;

    private static final class Lease implements ServiceConnection {
        final TermuxService owner;
        final Context context;
        final String id;
        final Runnable ready;
        final Interrupted interrupted;
        final String title, detail;
        boolean bound, connected, promoted, delivered;
        Z8PreparationService service;
        Lease(TermuxService owner, String id, String title, String detail, Runnable ready, Interrupted interrupted) {
            this.owner=owner; context=owner.getApplicationContext(); this.id=id;
            this.ready=ready; this.interrupted=interrupted; this.title=title; this.detail=detail;
        }
        @Override public void onServiceConnected(ComponentName name, IBinder binder) {
            if (LEASES.get(id)!=this) return;
            if (!(binder instanceof TermuxService.LocalBinder)
                    || ((TermuxService.LocalBinder)binder).service!=owner || owner.wantsToStop()) {
                cancel(this, stoppedMessage()); return;
            }
            connected=true; deliver(this);
        }
        @Override public void onServiceDisconnected(ComponentName name) { cancel(this, stoppedMessage()); }
        @Override public void onBindingDied(ComponentName name) { onServiceDisconnected(name); }
        @Override public void onNullBinding(ComponentName name) { onServiceDisconnected(name); }
        void release() {
            if (bound) { bound=false; try { context.unbindService(this); } catch (IllegalArgumentException ignored) {} }
        }
    }

    private static void mainThread() {
        if (Looper.myLooper()!=Looper.getMainLooper()) throw new IllegalStateException("Preparation leases stay on the main thread");
    }
    private static String stoppedMessage() {
        return Z8Text.text("Preparation stopped. Retry to validate completed steps. Your project files are preserved.",
            "준비가 중단되었습니다. 다시 시도하면 완료된 단계를 확인합니다. 프로젝트 파일은 보존됩니다.");
    }

    /** A worker may start only after Android accepts dataSync and the runtime binding is confirmed. */
    public static void begin(TermuxService owner, String id, Runnable ready, Interrupted interrupted) {
        begin(owner,id,null,null,ready,interrupted);
    }

    /** Explicit local file work shares the finite dataSync lifetime, with truthful progress text. */
    public static void beginFileTask(TermuxService owner, String id, String title, String detail,
            Runnable ready, Interrupted interrupted) {
        begin(owner,id,title,detail,ready,interrupted);
    }

    private static void begin(TermuxService owner, String id, String title, String detail,
            Runnable ready, Interrupted interrupted) {
        mainThread();
        if (owner.wantsToStop() || owner.z8IsStopRequested() || LEASES.containsKey(id))
            throw new IllegalStateException("Preparation cannot acquire this runtime");
        Lease lease=new Lease(owner,id,title,detail,ready,interrupted); LEASES.put(id,lease);
        try {
            lease.bound=lease.context.bindService(new Intent(lease.context,TermuxService.class),lease,Context.BIND_AUTO_CREATE);
            if (!lease.bound) throw new IllegalStateException("Could not retain preparation runtime");
            lease.context.startForegroundService(new Intent(lease.context,Z8PreparationService.class).putExtra(REQUEST,id));
        } catch (RuntimeException error) {
            LEASES.remove(id,lease); lease.release(); throw error;
        }
    }

    public static void finish(TermuxService owner, String id) {
        mainThread(); Lease lease=LEASES.get(id);
        if (lease==null || lease.owner!=owner) return;
        LEASES.remove(id); lease.release(); refresh(owner);
    }

    public static void releaseOwner(TermuxService owner) {
        mainThread();
        for (Lease lease:new ArrayList<>(LEASES.values())) if (lease.owner==owner) {
            try { cancel(lease,stoppedMessage()); }
            catch (RuntimeException ignored) { /* Continue stopping other owned work after an observer failure. */ }
        }
    }

    private static void deliver(Lease lease) {
        if (LEASES.get(lease.id)!=lease || !lease.connected || !lease.promoted || lease.delivered) return;
        lease.delivered=true;
        try { lease.ready.run(); }
        catch (RuntimeException failure) { cancel(lease, stoppedMessage()); }
    }

    private static void cancel(Lease lease, String message) {
        if (!LEASES.remove(lease.id,lease)) return;
        try { lease.interrupted.stopped(message); }
        finally { lease.release(); refresh(lease.owner); }
    }

    public static void refresh(TermuxService owner) {
        mainThread(); Z8PreparationService service=running;
        if (service==null || service.ending) return;
        if (LEASES.isEmpty()) service.end(null);
        else service.getSystemService(NotificationManager.class).notify(NOTIFICATION,service.notification());
    }

    @Override public IBinder onBind(Intent intent) { return null; }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent!=null && STOP.equals(intent.getAction())) { end(stoppedMessage()); return START_NOT_STICKY; }
        Lease lease=intent==null?null:LEASES.get(intent.getStringExtra(REQUEST));
        if (lease==null) {
            if (LEASES.isEmpty()) { if(running==this)end(null);else stopSelf(startId); }
            return START_NOT_STICKY;
        }
        if (ending) { cancel(lease,stoppedMessage()); stopSelf(startId); return START_NOT_STICKY; }
        running=this; lease.service=this;
        try {
            Notification notification=notification();
            if (Build.VERSION.SDK_INT>=29) startForeground(NOTIFICATION,notification,ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
            else startForeground(NOTIFICATION,notification);
            lease.promoted=true; deliver(lease);
        } catch (RuntimeException failure) { end(stoppedMessage()); }
        return START_NOT_STICKY;
    }

    /** API 35+: stop this timed-out service immediately; never stop interactive terminals. */
    @Override public void onTimeout(int startId, int foregroundServiceType) {
        if ((foregroundServiceType & ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)!=0)
            end(Z8Text.text("Android stopped preparation after its time limit. Retry when ready; completed steps and project files are preserved.",
                "Android가 제한 시간에 도달한 준비 작업을 중단했습니다. 준비되면 다시 시도해 주세요. 완료된 단계와 프로젝트 파일은 보존됩니다."));
    }

    private void end(String message) {
        if (ending) return;
        boolean wasCurrent=running==this;
        ending=true; if (wasCurrent) running=null;
        // Demote/stop before any worker cleanup; Android grants only a few seconds.
        stopForeground(STOP_FOREGROUND_REMOVE); stopSelf();
        if (message!=null) for (Lease lease:new ArrayList<>(LEASES.values()))
            if (lease.service==this || wasCurrent && lease.service==null) {
                try { cancel(lease,message); }
                catch (RuntimeException ignored) { /* One observer cannot prevent other workers from stopping. */ }
            }
    }

    @Override public void onDestroy() {
        if (!ending) end(stoppedMessage());
        super.onDestroy();
    }

    private Notification notification() {
        NotificationManager manager=getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel(CHANNEL,
            Z8Text.text("Project tasks","프로젝트 작업"),NotificationManager.IMPORTANCE_LOW));
        Notification.Builder builder=new Notification.Builder(this,CHANNEL).setSmallIcon(R.drawable.ic_service_notification)
            .setContentTitle(Z8Text.text("z8 · Preparing","z8 · 준비 중"))
            .setContentText(Z8Text.text("Preparing the selected local environment or tool","선택한 로컬 환경 또는 도구를 준비합니다"))
            .setCategory(Notification.CATEGORY_PROGRESS).setOngoing(true).setOnlyAlertOnce(true);
        for (Lease lease:LEASES.values()) {
            if (lease.title!=null) { builder.setContentTitle(lease.title).setContentText(lease.detail); break; }
            if (Z8PreparationNotification.decorate(builder,lease.owner)) break;
        }
        PendingIntent stop=PendingIntent.getService(this,0,new Intent(this,Z8PreparationService.class).setAction(STOP),
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        builder.addAction(0,Z8Text.text("Stop tasks","작업 중지"),stop);
        return builder.build();
    }
}
