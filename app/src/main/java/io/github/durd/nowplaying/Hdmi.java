package io.github.durd.nowplaying;

import android.content.Context;
import android.media.tv.TvInputInfo;
import android.media.tv.TvInputManager;
import android.util.Log;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.util.HashMap;
import java.util.Map;

/**
 * Whether an HDMI source is on screen, and what it is called. Nothing else about it is knowable from the
 * TV (a set-top box never says which channel it shows), so it is reported as "on".
 *
 * HDMI-CEC itself is out of reach: SELinux keeps apps from finding the hdmi_control service, DUMP or
 * not. The TV input framework is not: `dumpsys tv_input` names the input of the main session (the one on
 * screen), and TvInputManager labels it ("HDMI 1"). A CEC device is registered as a child input of its
 * port, labelled with the device's own CEC name (a set-top box's model, say). The main session outlives the input being on
 * screen (it stays while Netflix is in front), so the focused app must be the input viewer too. That
 * comes from `dumpsys window displays`; `dumpsys activity` refuses apps even with DUMP and the
 * usage-stats app-op.
 *
 *     mainSessionToken: android.os.Binder@51cb176
 *     sessionStateMap: ...
 *       inputId: com.mediatek.tvinput/.hdmi.HDMIInputService/HW5
 *       sessionToken: android.os.Binder@51cb176
 */
final class Hdmi {
    private static final String VIEWER = "org.droidtv.playtv";

    private Hdmi() {
    }

    /** An "on" report for the HDMI source on screen, or null when none is. */
    static NowPlayingListener.Report read(Context context) {
        try {
            String inputId = mainInput();
            if (inputId == null) return null;
            TvInputManager tv = context.getSystemService(TvInputManager.class);
            TvInputInfo input = tv.getTvInputInfo(inputId);
            if (input == null || input.getType() != TvInputInfo.TYPE_HDMI) return null;
            // The input session stays open while another app is in front, so check what has focus.
            String front = focusedApp();
            if (!VIEWER.equals(front)) return null;
            NowPlayingListener.Report r = new NowPlayingListener.Report();
            r.state = "on";
            r.app = VIEWER;
            r.title = label(context, input);
            // The CEC device behind this port, if it has one.
            for (TvInputInfo child : tv.getTvInputList()) {
                if (input.getId().equals(child.getParentId())) {
                    r.appName = label(context, child);
                    break;
                }
            }
            if (r.appName == null) r.appName = r.title;
            return r;
        } catch (Exception e) {
            Log.w(NowPlayingListener.TAG, "reading the TV input failed", e);
            return null;
        }
    }

    /**
     * The input's own label ("HDMI 1"), not its custom label: Philips stores the icon the user picked
     * for the input there, as "HD Digital Receiver&HD_DIGITAL_RECEIVER".
     */
    private static String label(Context context, TvInputInfo info) {
        return info.loadLabel(context).toString();
    }

    /** Input id of the main (on-screen) TV input session, from `dumpsys tv_input`. */
    private static String mainInput() throws Exception {
        String mainToken = null;
        String inputId = null;
        // Sessions are listed before mainSessionToken: keep each session's input until it is known.
        Map<String, String> inputOf = new HashMap<>();
        Process p = new ProcessBuilder("dumpsys", "tv_input").redirectErrorStream(true).start();
        try (BufferedReader in = new BufferedReader(new InputStreamReader(p.getInputStream()))) {
            for (String line; (line = in.readLine()) != null; ) {
                line = line.trim();
                if (line.startsWith("mainSessionToken: ")) mainToken = line.substring("mainSessionToken: ".length());
                else if (line.startsWith("inputId: ")) inputId = line.substring("inputId: ".length());
                else if (line.startsWith("sessionToken: ")) inputOf.put(line.substring("sessionToken: ".length()), inputId);
            }
        }
        p.waitFor();
        return mainToken == null ? null : inputOf.get(mainToken);
    }

    /** Package of the focused app, from `dumpsys window displays`. */
    private static String focusedApp() throws Exception {
        Process p = new ProcessBuilder("dumpsys", "window", "displays").redirectErrorStream(true).start();
        try (BufferedReader in = new BufferedReader(new InputStreamReader(p.getInputStream()))) {
            for (String line; (line = in.readLine()) != null; ) {
                // mFocusedApp=ActivityRecord{3faeefc u0 org.droidtv.playtv/.PlayTvActivity t24}
                int at = line.indexOf("mFocusedApp=ActivityRecord{");
                if (at < 0) continue;
                String[] f = line.substring(at).split(" ");
                return f.length > 2 ? f[2].split("/")[0] : null;
            }
            return null;
        } finally {
            p.destroy();   // the rest of the dump is not needed
        }
    }
}
