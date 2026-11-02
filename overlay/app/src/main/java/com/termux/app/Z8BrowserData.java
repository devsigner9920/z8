package com.termux.app;

import android.os.Looper;
import android.webkit.WebStorage;
import androidx.webkit.WebStorageCompat;
import androidx.webkit.WebViewFeature;

/** Clears only z8's default WebView profile, never browser Custom Tabs or CLI files. */
final class Z8BrowserData {
    private Z8BrowserData() {}
    private static final Z8PreviewDataOperation operation = new Z8PreviewDataOperation(new Z8PreviewDataOperation.Backend() {
        @Override public boolean supported() {
            return WebViewFeature.isFeatureSupported(WebViewFeature.DELETE_BROWSING_DATA);
        }
        @Override public void stopPreviews() { Z8BrowserPane.stopPreviewsForDataDeletion(); }
        @Override public void delete(Runnable completed) {
            // Unlike WebStorage.deleteAllData(), this API includes cookies, cache and service workers
            // and supplies a completion callback. Never infer completion from an empty Web SQL list.
            WebStorageCompat.deleteBrowsingData(WebStorage.getInstance(), completed);
        }
    });
    static {
        operation.observe(() -> {
            if (!operation.running()) Z8BrowserPane.finishPreviewDataDeletion(operation.state() == Z8PreviewDataOperation.State.COMPLETE);
        });
    }

    static boolean running() { return operation.running(); }
    static void observe(Runnable observer) { checkMain(); operation.observe(observer); }
    static void forget(Runnable observer) { checkMain(); operation.forget(observer); }
    static void clear() { checkMain(); operation.start(); }
    static String status() {
        switch (operation.state()) {
            case RUNNING: return "미리보기 데이터 삭제 중… 완료를 확인하고 있어요.";
            case COMPLETE: return "미리보기 데이터 삭제를 완료했습니다. 다시 방문하면 데이터가 새로 저장될 수 있습니다.";
            case UNSUPPORTED: return "현재 Android System WebView는 전체 데이터 삭제를 지원하지 않습니다. WebView를 업데이트한 뒤 다시 시도해 주세요. 데이터는 삭제하지 않았습니다.";
            case FAILED: return "미리보기 데이터 삭제를 완료했는지 확인할 수 없습니다. 다시 시도해 주세요.";
            default: return "모든 프로젝트의 미리보기 쿠키·사이트 저장소·캐시";
        }
    }
    private static void checkMain() {
        if (Looper.myLooper() != Looper.getMainLooper()) throw new IllegalStateException("Preview data operation requires the UI thread");
    }
}
