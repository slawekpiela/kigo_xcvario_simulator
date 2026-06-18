package pl.kigo.xcvario.bridge;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

public final class MainActivity extends Activity {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextView statusView;

    private final Runnable refreshStatus = new Runnable() {
        @Override
        public void run() {
            if (statusView != null) {
                statusView.setText(BridgeService.snapshot());
            }
            handler.postDelayed(this, 1000L);
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(buildContent());
    }

    @Override
    protected void onResume() {
        super.onResume();
        refreshStatus.run();
    }

    @Override
    protected void onPause() {
        handler.removeCallbacks(refreshStatus);
        super.onPause();
    }

    private View buildContent() {
        ScrollView scroll = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(20), dp(20), dp(20), dp(20));
        scroll.addView(root);

        TextView title = new TextView(this);
        title.setText(getString(R.string.app_name));
        title.setTextSize(24);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        root.addView(title, matchWrap());

        TextView summary = new TextView(this);
        summary.setText("Local TCP bridge for Kigo/Nav. Configure Kigo/Nav to use 127.0.0.1:4353 and FLARM 127.0.0.1:4354.");
        summary.setPadding(0, dp(8), 0, dp(12));
        root.addView(summary, matchWrap());

        LinearLayout buttons = new LinearLayout(this);
        buttons.setGravity(Gravity.START);
        buttons.setOrientation(LinearLayout.HORIZONTAL);
        root.addView(buttons, matchWrap());

        Button start = new Button(this);
        start.setText("Start");
        start.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                startBridgeService();
            }
        });
        buttons.addView(start);

        Button stop = new Button(this);
        stop.setText("Stop");
        stop.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                stopBridgeService();
            }
        });
        buttons.addView(stop);

        statusView = new TextView(this);
        statusView.setTypeface(Typeface.MONOSPACE);
        statusView.setTextSize(14);
        statusView.setPadding(0, dp(16), 0, dp(16));
        root.addView(statusView, matchWrap());

        TextView commands = new TextView(this);
        commands.setTypeface(Typeface.MONOSPACE);
        commands.setText(
                "Mac commands:\n" +
                "adb reverse tcp:44353 tcp:4353\n" +
                "adb reverse tcp:44354 tcp:4354\n\n" +
                "Android bridge:\n" +
                "listen 127.0.0.1:4353 -> upstream 127.0.0.1:44353\n" +
                "listen 127.0.0.1:4354 -> upstream 127.0.0.1:44354"
        );
        root.addView(commands, matchWrap());

        return scroll;
    }

    private void startBridgeService() {
        Intent intent = new Intent(this, BridgeService.class);
        intent.setAction(BridgeService.ACTION_START);
        if (Build.VERSION.SDK_INT >= 26) {
            startForegroundService(intent);
        } else {
            startService(intent);
        }
    }

    private void stopBridgeService() {
        Intent intent = new Intent(this, BridgeService.class);
        intent.setAction(BridgeService.ACTION_STOP);
        startService(intent);
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        );
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
