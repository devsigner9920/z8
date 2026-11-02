package com.termux.app;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.BitmapShader;
import android.graphics.Canvas;
import android.graphics.ColorFilter;
import android.graphics.Matrix;
import android.graphics.Paint;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.graphics.RectF;
import android.graphics.Shader;
import android.graphics.drawable.Drawable;
import android.util.Log;

import java.io.IOException;
import java.io.InputStream;

/** Static, center-cropped rendering of the user-supplied Prism reference image. */
public final class Z8SpectrumDrawable extends Drawable {
    private static final String ASSET = "z8/design/prism-reference.png";
    private static final Object BITMAP_LOCK = new Object();
    private static volatile boolean loadAttempted;
    private static Bitmap sharedBitmap;

    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG | Paint.FILTER_BITMAP_FLAG);
    private final RectF drawingBounds = new RectF();
    private final Matrix matrix = new Matrix();
    private final float radius;
    private final Bitmap bitmap;
    private final BitmapShader shader;

    public Z8SpectrumDrawable(Context context, int radiusDp) {
        radius = Math.max(0, radiusDp) * context.getResources().getDisplayMetrics().density;
        // Decoding happens once here, never during draw(), bounds changes, or animation frames.
        bitmap = bitmap(context.getApplicationContext());
        shader = bitmap == null ? null : new BitmapShader(bitmap, Shader.TileMode.CLAMP, Shader.TileMode.CLAMP);
        if (shader != null) paint.setShader(shader);
        else paint.setColor(0xffb19aff); // Keep controls readable if the packaged asset is unavailable.
    }

    private static Bitmap bitmap(Context application) {
        if (loadAttempted) return sharedBitmap;
        synchronized (BITMAP_LOCK) {
            if (loadAttempted) return sharedBitmap;
            BitmapFactory.Options options = new BitmapFactory.Options();
            options.inSampleSize = 4;
            options.inPreferredConfig = Bitmap.Config.ARGB_8888;
            options.inScaled = false;
            // The 1800 x 2774 asset decodes to about 450 x 694 pixels: under 1.3 MiB.
            try (InputStream input = application.getAssets().open(ASSET)) {
                sharedBitmap = BitmapFactory.decodeStream(input, null, options);
                if (sharedBitmap == null) Log.w("Z8SpectrumDrawable", "Prism reference image could not be decoded");
            } catch (IOException exception) {
                Log.w("Z8SpectrumDrawable", "Prism reference image is unavailable", exception);
            }
            loadAttempted = true;
            return sharedBitmap;
        }
    }

    @Override protected void onBoundsChange(Rect bounds) {
        drawingBounds.set(bounds);
        if (shader == null || bounds.isEmpty()) return;
        float scale = Math.max((float) bounds.width() / bitmap.getWidth(), (float) bounds.height() / bitmap.getHeight());
        float left = bounds.left + (bounds.width() - bitmap.getWidth() * scale) / 2f;
        float top = bounds.top + (bounds.height() - bitmap.getHeight() * scale) / 2f;
        matrix.setScale(scale, scale);
        matrix.postTranslate(left, top);
        shader.setLocalMatrix(matrix);
    }

    @Override public void draw(Canvas canvas) {
        canvas.drawRoundRect(drawingBounds, radius, radius, paint);
    }

    @Override public void setAlpha(int alpha) { paint.setAlpha(alpha); invalidateSelf(); }
    @Override public int getAlpha() { return paint.getAlpha(); }
    @Override public void setColorFilter(ColorFilter filter) { paint.setColorFilter(filter); invalidateSelf(); }
    @Override public int getOpacity() { return PixelFormat.TRANSLUCENT; }
}
