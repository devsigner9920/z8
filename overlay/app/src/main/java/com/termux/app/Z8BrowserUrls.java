package com.termux.app;

import java.net.URI;
import java.util.Locale;

/** URL boundary shared by the address field and WebView navigation. Never logs URLs. */
public final class Z8BrowserUrls {
    public enum RequestTarget { BLANK, PREVIEW, EXTERNAL, INVALID }
    private Z8BrowserUrls() {}

    /** An explicit empty-tab action, never a WebView or external navigation URL. */
    public static boolean isBlank(String value) { return "about:blank".equals(value); }

    public static RequestTarget requestTarget(String value) {
        if (isBlank(value)) return RequestTarget.BLANK;
        String url = normalize(value);
        if (url == null) return RequestTarget.INVALID;
        return isPreview(url) ? RequestTarget.PREVIEW : RequestTarget.EXTERNAL;
    }

    public static String normalize(String value) {
        if (value == null) return null;
        String url = value.trim();
        if (url.isEmpty() || url.length() > 8192 || url.indexOf('\\') >= 0) return null;
        for (int i = 0; i < url.length(); i++) if (Character.isISOControl(url.charAt(i))) return null;
        if (!url.contains("://")) url = "http://" + url;
        try {
            URI parsed = new URI(url);
            String scheme = parsed.getScheme();
            if (!("https".equalsIgnoreCase(scheme) || "http".equalsIgnoreCase(scheme))
                    || parsed.getHost() == null || parsed.getRawUserInfo() != null
                    || parsed.getPort() > 65535 || parsed.getPort() == 0) return null;
            return parsed.toASCIIString();
        } catch (Exception invalid) { return null; }
    }

    public static boolean isPreview(String value) {
        String url = normalize(value);
        if (url == null) return false;
        String host = URI.create(url).getHost().toLowerCase(Locale.ROOT);
        return host.equals("localhost") || host.equals("127.0.0.1")
            || host.equals("[::1]") || host.equals("::1");
    }

    /** Host only: authentication query strings never become tab labels. */
    public static String host(String value) {
        String url = normalize(value);
        return url == null ? "브라우저" : URI.create(url).getHost();
    }
}
