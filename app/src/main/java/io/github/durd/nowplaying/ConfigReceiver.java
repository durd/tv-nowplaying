package io.github.durd.nowplaying;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.util.Log;

/**
 * Takes the settings over ADB, since the app has no UI:
 *
 *     am broadcast --include-stopped-packages -n io.github.durd.nowplaying/.ConfigReceiver \
 *         --es webhook_id <id> [--es ha_url http://host:port]
 *
 * The manifest only lets senders holding android.permission.DUMP in: ADB's shell (Home Assistant's
 * Android Debug Bridge integration, install.sh), not other apps on the TV. An empty ha_url goes back to
 * finding Home Assistant over mDNS. The webhook id is never logged.
 */
public class ConfigReceiver extends BroadcastReceiver {
    static final String WEBHOOK_ID = "webhook_id";
    static final String HA_URL = "ha_url";

    static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences("config", Context.MODE_PRIVATE);
    }

    @Override
    public void onReceive(Context context, Intent intent) {
        SharedPreferences.Editor edit = prefs(context).edit();
        String id = intent.getStringExtra(WEBHOOK_ID);
        if (id != null) edit.putString(WEBHOOK_ID, id.trim());
        if (intent.hasExtra(HA_URL)) edit.putString(HA_URL, intent.getStringExtra(HA_URL).trim());
        edit.commit();
        Log.i(NowPlayingListener.TAG, "configured: webhook id " + (id == null ? "unchanged" : "set")
                + ", Home Assistant " + (prefs(context).getString(HA_URL, "").isEmpty() ? "over mDNS" : "set"));
        setResultData("ok");
        NowPlayingListener.reconfigure();
    }
}
