package io.github.durd.nowplaying;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.media.AudioManager;
import android.media.AudioPlaybackConfiguration;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.PowerManager;
import android.os.SystemClock;
import android.service.notification.NotificationListenerService;
import android.util.Log;

import java.util.List;
import java.util.Objects;

/**
 * Reports what the TV is playing to a Home Assistant webhook.
 *
 * A notification listener only because the system binds it at boot and keeps it bound; its own
 * session API (getActiveSessions) is not used, since it leaves out sessions an app never marks active,
 * and SmartTube never does. The sessions come from `dumpsys media_session` instead, which needs
 * android.permission.DUMP granted over ADB (install.sh does both grants).
 *
 * Polls every POLL_MS while the screen is on, plus right after any audio player starts or stops, and
 * sends only when something changed. Screen off sends a final "off".
 */
public class NowPlayingListener extends NotificationListenerService {
    static final String TAG = "NowPlaying";
    private static final long POLL_MS = 5000;
    // A position further than this from where the last report says it should be is a seek: report it.
    private static final long SEEK_MS = 3000;

    // Written on the main thread, read on the poll thread.
    private volatile HandlerThread thread;
    private volatile Handler handler;
    private Webhook webhook;
    private Report last;
    private long lastSentAt;   // elapsedRealtime of the last send

    private final Runnable poll = new Runnable() {
        @Override
        public void run() {
            // A poll left over from before a disconnect (it may have been blocked in discovery) stops here.
            if (!current()) return;
            handler.removeCallbacks(this);
            if (getSystemService(PowerManager.class).isInteractive()) {
                check(read());
                handler.postDelayed(this, POLL_MS);
            } else {
                check(Report.off());
            }
        }
    };

    private final BroadcastReceiver screen = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            handler.post(poll);
        }
    };

    // Fires for other apps' players too (their details are redacted, which is fine: it is only a nudge).
    private final AudioManager.AudioPlaybackCallback audio = new AudioManager.AudioPlaybackCallback() {
        @Override
        public void onPlaybackConfigChanged(List<AudioPlaybackConfiguration> configs) {
            Log.d(TAG, "audio players changed: " + configs.size());
            // Give the app a moment to update its session after its player changes.
            handler.removeCallbacks(poll);
            handler.postDelayed(poll, 500);
        }
    };

    // Regranting access binds a new instance without disconnecting the old one, so which instance
    // polls is decided process-wide: the last one connected.
    private static volatile NowPlayingListener owner;

    @Override
    public void onListenerConnected() {
        // The system can connect a listener more than once (a rebind after access is regranted).
        if (thread != null) return;
        Log.i(TAG, "listener connected");
        NowPlayingListener previous = owner;
        owner = this;
        if (previous != null && previous != this) previous.onListenerDisconnected();
        thread = new HandlerThread("nowplaying");
        thread.start();
        handler = new Handler(thread.getLooper());
        webhook = new Webhook(this);
        IntentFilter f = new IntentFilter(Intent.ACTION_SCREEN_ON);
        f.addAction(Intent.ACTION_SCREEN_OFF);
        registerReceiver(screen, f, null, handler);
        getSystemService(AudioManager.class).registerAudioPlaybackCallback(audio, handler);
        handler.post(poll);
    }

    @Override
    public void onListenerDisconnected() {
        if (thread == null) return;
        Log.i(TAG, "listener disconnected");
        unregisterReceiver(screen);
        getSystemService(AudioManager.class).unregisterAudioPlaybackCallback(audio);
        thread.quitSafely();
        thread = null;
        last = null;
    }

    /** New settings from ConfigReceiver: find Home Assistant again and report afresh. */
    static void reconfigure() {
        NowPlayingListener l = owner;
        Handler h = l == null ? null : l.handler;
        if (h == null) return;   // not connected yet; the first poll reads the settings anyway
        h.post(() -> {
            l.webhook = new Webhook(l);
            l.last = null;
            h.post(l.poll);
        });
    }

    @Override
    public void onDestroy() {
        onListenerDisconnected();
        if (owner == this) owner = null;
        super.onDestroy();
    }

    /**
     * A playing app first, then an HDMI source on screen, then a paused app (one left paused in the
     * background should not outrank what is on screen), then idle.
     */
    private Report read() {
        Report session = Sessions.read();
        if (session == null || "playing".equals(session.state)) return session;
        Report hdmi = Hdmi.read(this);
        return hdmi != null ? hdmi : session;
    }

    private void check(Report now) {
        if (now == null) return;   // dumpsys failed; already logged, try again next poll
        if (last != null && now.sameAs(last) && !seeked(now)) return;
        if (now.appName == null) now.appName = label(now.app);
        // Discovery can block for seconds; a disconnect meanwhile hands the job to a new poll thread.
        if (!webhook.connect() || !current()) return;
        if (webhook.send(now)) {
            last = now;
            lastSentAt = SystemClock.elapsedRealtime();
        }
    }

    /** Whether the calling thread is the poll thread of the current connection. */
    private boolean current() {
        Handler h = handler;
        return owner == this && thread != null && h != null && h.getLooper() == android.os.Looper.myLooper();
    }

    private boolean seeked(Report now) {
        if (now.positionMs < 0 || last.positionMs < 0) return false;
        long expected = last.positionMs;
        if ("playing".equals(last.state)) expected += SystemClock.elapsedRealtime() - lastSentAt;
        return Math.abs(now.positionMs - expected) > SEEK_MS;
    }

    private String label(String pkg) {
        if (pkg == null) return null;
        PackageManager pm = getPackageManager();
        try {
            return pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString();
        } catch (PackageManager.NameNotFoundException e) {
            return pkg;
        }
    }

    /** What is sent to Home Assistant. */
    static class Report {
        String state;        // playing, paused, idle, off
        String app;          // package name
        String appName;
        String title;
        String artist;       // channel for YouTube, show or artist where the app gives one
        long positionMs = -1;

        static Report off() {
            Report r = new Report();
            r.state = "off";
            return r;
        }

        boolean sameAs(Report o) {
            return state.equals(o.state) && Objects.equals(app, o.app)
                    && Objects.equals(title, o.title) && Objects.equals(artist, o.artist);
        }
    }
}
