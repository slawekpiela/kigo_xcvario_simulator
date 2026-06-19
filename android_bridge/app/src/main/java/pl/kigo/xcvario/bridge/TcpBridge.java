package pl.kigo.xcvario.bridge;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.concurrent.atomic.AtomicLong;

final class TcpBridge {
    private final String name;
    private final int listenPort;
    private final String upstreamHost;
    private final int upstreamPort;
    private final AtomicLong upstreamToDeviceBytes = new AtomicLong();
    private final AtomicLong deviceToUpstreamBytes = new AtomicLong();
    private final AtomicLong lastTransmissionMillis = new AtomicLong();

    private volatile boolean running;
    private volatile String status = "stopped";
    private volatile ServerSocket serverSocket;
    private volatile Socket currentDeviceSocket;
    private volatile Socket currentUpstreamSocket;
    private Thread worker;

    TcpBridge(String name, int listenPort, String upstreamHost, int upstreamPort) {
        this.name = name;
        this.listenPort = listenPort;
        this.upstreamHost = upstreamHost;
        this.upstreamPort = upstreamPort;
    }

    void start() {
        if (running) {
            return;
        }
        running = true;
        worker = new Thread(new Runnable() {
            @Override
            public void run() {
                runServer();
            }
        }, "kigo-" + name + "-bridge");
        worker.start();
    }

    void stop() {
        running = false;
        closeQuietly(currentDeviceSocket);
        closeQuietly(currentUpstreamSocket);
        closeQuietly(serverSocket);
        lastTransmissionMillis.set(0L);
        status = "stopped";
    }

    String snapshot(long nowMillis) {
        return name
                + " listen=127.0.0.1:" + listenPort
                + " upstream=" + upstreamHost + ":" + upstreamPort
                + " connected=" + yesNo(isConnected())
                + " transmitting=" + yesNo(isTransmitting(nowMillis))
                + " status=" + status
                + " upstream_to_device=" + upstreamToDeviceBytes.get()
                + " device_to_upstream=" + deviceToUpstreamBytes.get();
    }

    boolean isConnected() {
        return "bridging".equals(status);
    }

    boolean isTransmitting(long nowMillis) {
        long lastTransmission = lastTransmissionMillis.get();
        return isConnected() && lastTransmission > 0L && nowMillis - lastTransmission <= 2500L;
    }

    private void runServer() {
        ServerSocket server = null;
        try {
            server = new ServerSocket();
            server.setReuseAddress(true);
            server.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), listenPort));
            serverSocket = server;
            status = "listening";

            while (running) {
                Socket deviceSocket = server.accept();
                handleDevice(deviceSocket);
            }
        } catch (IOException error) {
            if (running) {
                status = "server error: " + error.getMessage();
            }
        } finally {
            closeQuietly(server);
            serverSocket = null;
        }
    }

    private void handleDevice(Socket deviceSocket) {
        Socket upstreamSocket = null;
        try {
            currentDeviceSocket = deviceSocket;
            deviceSocket.setTcpNoDelay(true);
            status = "device connected";

            upstreamSocket = new Socket();
            upstreamSocket.setTcpNoDelay(true);
            upstreamSocket.connect(new InetSocketAddress(upstreamHost, upstreamPort), 3000);
            currentUpstreamSocket = upstreamSocket;
            status = "bridging";

            Thread toDevice = copyThread(
                    upstreamSocket.getInputStream(),
                    deviceSocket.getOutputStream(),
                    upstreamToDeviceBytes,
                    "upstream-to-device"
            );
            Thread toUpstream = copyThread(
                    deviceSocket.getInputStream(),
                    upstreamSocket.getOutputStream(),
                    deviceToUpstreamBytes,
                    "device-to-upstream"
            );
            toDevice.start();
            toUpstream.start();

            while (running && toDevice.isAlive() && toUpstream.isAlive()) {
                sleep(200L);
            }
        } catch (IOException error) {
            if (running) {
                status = "upstream error: " + error.getMessage();
                sleep(1000L);
            }
        } finally {
            closeQuietly(deviceSocket);
            closeQuietly(upstreamSocket);
            currentDeviceSocket = null;
            currentUpstreamSocket = null;
            if (running) {
                status = "listening";
            }
        }
    }

    private Thread copyThread(
            final InputStream input,
            final OutputStream output,
            final AtomicLong byteCounter,
            String direction
    ) {
        return new Thread(new Runnable() {
            @Override
            public void run() {
                byte[] buffer = new byte[4096];
                try {
                    while (running) {
                        int read = input.read(buffer);
                        if (read < 0) {
                            break;
                        }
                        output.write(buffer, 0, read);
                        output.flush();
                        byteCounter.addAndGet(read);
                        lastTransmissionMillis.set(System.currentTimeMillis());
                    }
                } catch (IOException ignored) {
                    // Socket shutdown or client disconnect.
                }
            }
        }, "kigo-" + name + "-" + direction);
    }

    private void sleep(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException ignored) {
            Thread.currentThread().interrupt();
        }
    }

    private void closeQuietly(ServerSocket socket) {
        if (socket == null) {
            return;
        }
        try {
            socket.close();
        } catch (IOException ignored) {
            // Already closed.
        }
    }

    private void closeQuietly(Socket socket) {
        if (socket == null) {
            return;
        }
        try {
            socket.close();
        } catch (IOException ignored) {
            // Already closed.
        }
    }

    private String yesNo(boolean value) {
        return value ? "YES" : "NO";
    }
}
