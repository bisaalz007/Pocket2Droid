package com.samsixx.p2dforensics;
import android.app.Instrumentation;
import android.os.Bundle;
import android.os.Environment;
import java.io.*;
import java.security.MessageDigest;
import org.json.JSONObject;

/** Same-signer, one-shot read-only snapshot. Does not start an Activity or engine. */
public final class Snapshot extends Instrumentation {
    private Bundle args;
    public void onCreate(Bundle args) { this.args = args; start(); }
    private static String hash(File file) throws Exception {
        MessageDigest d = MessageDigest.getInstance("SHA-256");
        try (InputStream in = new FileInputStream(file)) {
            byte[] b = new byte[1048576]; int n;
            while ((n = in.read(b)) != -1) d.update(b, 0, n);
        }
        StringBuilder s = new StringBuilder();
        for (byte b : d.digest()) s.append(String.format(java.util.Locale.US, "%02x", b & 255));
        return s.toString();
    }
    public void onStart() {
        Bundle result = new Bundle();
        try {
            String name = args.getString("directory");
            if (name == null || !name.matches("Pocket2Droid-V653-Snapshot-[a-f0-9]{12}")) throw new IOException("Invalid snapshot directory");
            File target = new File(new File(Environment.getExternalStorageDirectory(), "Download"), name);
            if (target.exists() || !target.mkdir()) throw new IOException("Snapshot destination must be new");
            File source = new File(getTargetContext().getFilesDir(), "tcg-v1").getCanonicalFile();
            JSONObject report = new JSONObject().put("source", source.toString()).put("read_only_source", true);
            for (String f : new String[]{"ram-fmd.bin", "engine.log", "PPC_USA.BIN", "RagingThunder.cab"}) {
                File input = new File(source, f);
                if (!input.exists()) { report.put(f, "absent"); continue; }
                if (!input.getCanonicalFile().getParentFile().equals(source) || !input.isFile()) throw new IOException("Invalid input: " + f);
                if (f.equals("ram-fmd.bin") && input.length() != 33554432L) throw new IOException("Storage size mismatch");
                if (f.equals("engine.log") && input.length() > 1048576) throw new IOException("Unexpected log size");
                String before = hash(input);
                if (f.equals("ram-fmd.bin") || f.equals("engine.log")) {
                    File output = new File(target, f);
                    if (!output.createNewFile()) throw new IOException("Snapshot file exists");
                    try (InputStream in = new FileInputStream(input); FileOutputStream out = new FileOutputStream(output)) {
                        byte[] b = new byte[1048576]; int n;
                        while ((n = in.read(b)) != -1) out.write(b, 0, n);
                        out.getFD().sync();
                    }
                    if (!hash(output).equals(before)) throw new IOException("Copy mismatch");
                }
                if (!hash(input).equals(before)) throw new IOException("Source changed during snapshot");
                report.put(f, new JSONObject().put("bytes", input.length()).put("sha256", before));
            }
            try (FileOutputStream out = new FileOutputStream(new File(target, "snapshot.json"))) {
                out.write(report.toString(2).getBytes("UTF-8")); out.getFD().sync();
            }
            result.putString("snapshot", target.toString()); finish(0, result);
        } catch (Exception e) { result.putString("error", e.toString()); finish(1, result); }
    }
}
