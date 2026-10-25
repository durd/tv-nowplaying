package io.github.durd.nowplaying;

import android.os.SystemClock;
import android.util.Log;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Reads every media session from `dumpsys media_session` (Android 11 format) and picks the one to report.
 * Each session's block has, in order:
 *     package=org.smarttube.stable
 *     state=PlaybackState {state=3, position=851320, ..., speed=1.0, updated=7103757, ...}   or state=null
 *     metadata: size=7, description=<title>, <subtitle>, <description>                     or metadata: null
 */
final class Sessions {
    private static final Pattern STATE = Pattern.compile(
            "state=PlaybackState \\{state=(\\d+), position=(-?\\d+),.*? speed=(-?[\\d.]+), updated=(\\d+)");

    private Sessions() {
    }

    /** The playing session, else a paused one, else idle. Null when dumpsys could not be read. */
    static NowPlayingListener.Report read() {
        List<Session> all = parse();
        if (all == null) return null;
        Session pick = null;
        for (Session s : all) {
            if (s.state == 3) {
                pick = s;
                break;
            }
            if (s.state == 2 && pick == null) pick = s;
        }
        NowPlayingListener.Report r = new NowPlayingListener.Report();
        if (pick == null) {
            r.state = "idle";
            return r;
        }
        r.state = pick.state == 3 ? "playing" : "paused";
        r.app = pick.pkg;
        r.title = pick.title;
        r.artist = pick.artist;
        if (pick.positionMs >= 0) {
            // The app last set its position at `updated` (elapsedRealtime); a playing one has moved on since.
            long moved = pick.state == 3 ? (long) ((SystemClock.elapsedRealtime() - pick.updated) * pick.speed) : 0;
            r.positionMs = pick.positionMs + moved;
        }
        return r;
    }

    private static List<Session> parse() {
        List<Session> out = new ArrayList<>();
        try {
            Process p = new ProcessBuilder("dumpsys", "media_session").redirectErrorStream(true).start();
            try (BufferedReader in = new BufferedReader(new InputStreamReader(p.getInputStream()))) {
                Session cur = null;
                for (String line; (line = in.readLine()) != null; ) {
                    line = line.trim();
                    if (line.startsWith("package=")) {
                        cur = new Session();
                        cur.pkg = line.substring("package=".length());
                        out.add(cur);
                    } else if (cur == null) {
                        continue;
                    } else if (line.startsWith("state=PlaybackState")) {
                        Matcher m = STATE.matcher(line);
                        if (m.find()) {
                            cur.state = Integer.parseInt(m.group(1));
                            cur.positionMs = Long.parseLong(m.group(2));
                            cur.speed = Float.parseFloat(m.group(3));
                            cur.updated = Long.parseLong(m.group(4));
                        } else {
                            Log.w(NowPlayingListener.TAG, "unparsed: " + line);
                        }
                    } else if (line.startsWith("metadata:") && line.contains("description=")) {
                        cur.describe(line.substring(line.indexOf("description=") + "description=".length()));
                    }
                }
            }
            if (p.waitFor() != 0 || out.isEmpty()) {
                // No DUMP permission answers with a permission-denial line and no sessions.
                Log.w(NowPlayingListener.TAG, "dumpsys media_session gave no sessions; is DUMP granted?");
            }
            return out;
        } catch (Exception e) {
            Log.w(NowPlayingListener.TAG, "dumpsys media_session failed", e);
            return null;
        }
    }

    private static final class Session {
        String pkg;
        int state;
        long positionMs = -1;
        float speed;
        long updated;
        String title;
        String artist;

        /**
         * "<title>, <subtitle>, <description>", with "null" for a missing part. Any of the three can contain
         * ", " itself, so the split is a best guess. SmartTube's subtitle is
         * "<channel> • 1.2K views • Published on Mar 3, 2026": the channel is the part between the last ", "
         * before the first " • " and that " • ". Anything else splits from the right.
         */
        void describe(String d) {
            if (d.endsWith(", null")) d = d.substring(0, d.length() - ", null".length());
            int dot = d.indexOf(" • ");
            int cut = dot > 0 ? d.lastIndexOf(", ", dot) : -1;
            if (cut > 0) {
                title = part(d.substring(0, cut));
                artist = part(d.substring(cut + 2, dot));
                return;
            }
            int b = d.lastIndexOf(", ");
            if (b < 0) {
                title = part(d);
                return;
            }
            title = part(d.substring(0, b));
            artist = part(d.substring(b + 2));
        }

        private static String part(String s) {
            s = s.trim();
            return s.isEmpty() || s.equals("null") ? null : s;
        }
    }
}
