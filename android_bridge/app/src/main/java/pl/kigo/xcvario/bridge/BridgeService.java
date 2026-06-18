package pl.kigo.xcvario.bridge;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;

import java.util.ArrayList;
import java.util.List;

public final class BridgeService extends Service {
    static final String ACTION_START = "pl.kigo.xcvario.bridge.START";
    static final String ACTION_STOP = "pl.kigo.xcvario.bridge.STOP";

    private static final String CHANNEL_ID = "kigo_android_bridge";
    private static final int NOTIFICATION_ID = 4353;
    private static final Object LOCK = new Object();
    private static final List<TcpBridge> ACTIVE_BRIDGES = new ArrayList<TcpBridge>();
    private static volatile String lifecycleStatus = "stopped";

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            stopSelf();
            return START_NOT_STICKY;
        }

        createNotificationChannel();
        startForeground(NOTIFICATION_ID, buildNotification());
        startBridgesIfNeeded();
        return START_NOT_STICKY;
    }

    @Override
    public void onDestroy() {
        stopBridges();
        super.onDestroy();
    }

    static String snapshot() {
        StringBuilder text = new StringBuilder();
        text.append("service: ").append(lifecycleStatus).append('\n');
        synchronized (LOCK) {
            if (ACTIVE_BRIDGES.isEmpty()) {
                text.append("bridges: stopped\n");
            } else {
                for (TcpBridge bridge : ACTIVE_BRIDGES) {
                    text.append(bridge.snapshot()).append('\n');
                }
            }
        }
        return text.toString();
    }

    private void startBridgesIfNeeded() {
        synchronized (LOCK) {
            if (!ACTIVE_BRIDGES.isEmpty()) {
                lifecycleStatus = "running";
                return;
            }

            ACTIVE_BRIDGES.add(new TcpBridge("XCVario", 4353, "127.0.0.1", 44353));
            ACTIVE_BRIDGES.add(new TcpBridge("FLARM", 4354, "127.0.0.1", 44354));
            for (TcpBridge bridge : ACTIVE_BRIDGES) {
                bridge.start();
            }
            lifecycleStatus = "running";
        }
    }

    private void stopBridges() {
        synchronized (LOCK) {
            for (TcpBridge bridge : ACTIVE_BRIDGES) {
                bridge.stop();
            }
            ACTIVE_BRIDGES.clear();
            lifecycleStatus = "stopped";
        }
    }

    private Notification buildNotification() {
        Intent activityIntent = new Intent(this, MainActivity.class);
        PendingIntent pendingIntent = PendingIntent.getActivity(
                this,
                0,
                activityIntent,
                pendingIntentFlags()
        );

        Notification.Builder builder = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);

        return builder
                .setContentTitle(getString(R.string.app_name))
                .setContentText("127.0.0.1:4353/4354 -> adb reverse 44353/44354")
                .setSmallIcon(R.drawable.ic_bridge)
                .setContentIntent(pendingIntent)
                .setOngoing(true)
                .build();
    }

    private int pendingIntentFlags() {
        if (Build.VERSION.SDK_INT >= 23) {
            return PendingIntent.FLAG_IMMUTABLE;
        }
        return 0;
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT < 26) {
            return;
        }
        NotificationManager manager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (manager == null || manager.getNotificationChannel(CHANNEL_ID) != null) {
            return;
        }
        NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                getString(R.string.app_name),
                NotificationManager.IMPORTANCE_LOW
        );
        manager.createNotificationChannel(channel);
    }
}
