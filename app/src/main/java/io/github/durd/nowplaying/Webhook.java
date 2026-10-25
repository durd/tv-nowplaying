package io.github.durd.nowplaying;

import android.content.Context;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;
import android.util.Log;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/**
 * POSTs reports to Home Assistant's webhook endpoint. HA is found over mDNS (_home-assistant._tcp) and
 * reached at the address and port it advertises rather than its internal_url, which may be a reverse proxy.
 * The webhook id, and optionally a Home Assistant URL that skips discovery, come from ConfigReceiver.
 */
final class Webhook {
    private static final String SERVICE = "_home-assistant._tcp";
    private static final long DISCOVER_S = 10;

    private final Context context;
    private String base;   // e.g. http://192.0.2.10:8123, found again after a failed send

    Webhook(Context context) {
        this.context = context;
    }

    /** Finds Home Assistant if it is not known yet. Blocks for up to DISCOVER_S; call off the main thread. */
    boolean connect() {
        if (webhookId().isEmpty()) {
            Log.w(NowPlayingListener.TAG, "no webhook id yet; see ConfigReceiver");
            return false;
        }
        String url = ConfigReceiver.prefs(context).getString(ConfigReceiver.HA_URL, "");
        if (base == null) base = url.isEmpty() ? discover() : url;
        return base != null;
    }

    /** Blocks; call off the main thread, after connect(). True when HA accepted it. */
    boolean send(NowPlayingListener.Report r) {
        if (base == null) return false;
        HttpURLConnection c = null;
        try {
            byte[] body = json(r, version()).toString().getBytes(StandardCharsets.UTF_8);
            c = (HttpURLConnection) new URL(base + "/api/webhook/" + webhookId()).openConnection();
            c.setConnectTimeout(5000);
            c.setReadTimeout(5000);
            c.setDoOutput(true);
            c.setRequestProperty("Content-Type", "application/json");
            try (OutputStream out = c.getOutputStream()) {
                out.write(body);
            }
            int code = c.getResponseCode();
            Log.i(NowPlayingListener.TAG, "sent " + r.state + " " + r.app + " \"" + r.title + "\" at "
                    + r.positionMs + " ms -> " + code);
            // HA answers 200 for any webhook id, known or not, so this only proves HA is there.
            if (code == 200) return true;
        } catch (Exception e) {
            Log.w(NowPlayingListener.TAG, "send to " + base + " failed: " + e);
        } finally {
            if (c != null) c.disconnect();
        }
        base = null;
        return false;
    }

    private String webhookId() {
        return ConfigReceiver.prefs(context).getString(ConfigReceiver.WEBHOOK_ID, "");
    }

    /** This app's version, so Home Assistant knows what is installed. */
    private String version() {
        try {
            return context.getPackageManager().getPackageInfo(context.getPackageName(), 0).versionName;
        } catch (android.content.pm.PackageManager.NameNotFoundException e) {
            return null;
        }
    }

    private static JSONObject json(NowPlayingListener.Report r, String version) throws JSONException {
        JSONObject j = new JSONObject();
        j.put("version", version == null ? JSONObject.NULL : version);
        j.put("state", r.state);
        j.put("app", r.app == null ? JSONObject.NULL : r.app);
        j.put("app_name", r.appName == null ? JSONObject.NULL : r.appName);
        j.put("title", r.title == null ? JSONObject.NULL : r.title);
        j.put("artist", r.artist == null ? JSONObject.NULL : r.artist);
        j.put("position", r.positionMs < 0 ? JSONObject.NULL : r.positionMs / 1000.0);
        j.put("position_updated_at", Instant.now().toString());
        return j;
    }

    /** The first Home Assistant on the network, as http://host:port, or null. */
    private String discover() {
        NsdManager nsd = context.getSystemService(NsdManager.class);
        AtomicReference<String> found = new AtomicReference<>();
        CountDownLatch done = new CountDownLatch(1);
        NsdManager.DiscoveryListener browse = new NsdManager.DiscoveryListener() {
            @Override
            public void onServiceFound(NsdServiceInfo info) {
                if (done.getCount() == 0) return;
                nsd.resolveService(info, new NsdManager.ResolveListener() {
                    @Override
                    public void onServiceResolved(NsdServiceInfo s) {
                        String host = s.getHost().getHostAddress();
                        if (host.contains(":")) host = "[" + host.split("%")[0] + "]";   // IPv6 literal
                        found.compareAndSet(null, "http://" + host + ":" + s.getPort());
                        done.countDown();
                    }

                    @Override
                    public void onResolveFailed(NsdServiceInfo s, int error) {
                        Log.w(NowPlayingListener.TAG, "resolve " + s.getServiceName() + " failed: " + error);
                    }
                });
            }

            @Override
            public void onStartDiscoveryFailed(String type, int error) {
                Log.w(NowPlayingListener.TAG, "mDNS discovery failed: " + error);
                done.countDown();
            }

            @Override public void onDiscoveryStarted(String type) { }
            @Override public void onServiceLost(NsdServiceInfo info) { }
            @Override public void onDiscoveryStopped(String type) { }
            @Override public void onStopDiscoveryFailed(String type, int error) { }
        };
        nsd.discoverServices(SERVICE, NsdManager.PROTOCOL_DNS_SD, browse);
        try {
            done.await(DISCOVER_S, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        try {
            nsd.stopServiceDiscovery(browse);
        } catch (IllegalArgumentException ignored) {
            // discovery never started
        }
        Log.i(NowPlayingListener.TAG, "Home Assistant: " + found.get());
        return found.get();
    }
}
