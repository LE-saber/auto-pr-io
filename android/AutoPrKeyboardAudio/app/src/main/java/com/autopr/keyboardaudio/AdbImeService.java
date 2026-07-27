package com.autopr.keyboardaudio;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.inputmethodservice.InputMethodService;
import android.os.Build;
import android.util.Base64;
import android.view.inputmethod.InputConnection;

import java.nio.charset.StandardCharsets;

public class AdbImeService extends InputMethodService {
    public static final String ACTION_INPUT_TEXT = "ADB_INPUT_TEXT";
    public static final String ACTION_INPUT_B64 = "ADB_INPUT_B64";
    private BroadcastReceiver receiver;

    @Override
    public void onCreate() {
        super.onCreate();
        receiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                String action = intent.getAction();
                String text = intent.getStringExtra("msg");
                if (ACTION_INPUT_B64.equals(action) && text != null) {
                    byte[] decoded = Base64.decode(text, Base64.DEFAULT);
                    text = new String(decoded, StandardCharsets.UTF_8);
                }
                if (text != null) {
                    InputConnection ic = getCurrentInputConnection();
                    if (ic != null) {
                        ic.commitText(text, 1);
                    }
                }
            }
        };
        IntentFilter filter = new IntentFilter();
        filter.addAction(ACTION_INPUT_TEXT);
        filter.addAction(ACTION_INPUT_B64);
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(receiver, filter, Context.RECEIVER_EXPORTED);
        } else {
            registerReceiver(receiver, filter);
        }
    }

    @Override
    public void onDestroy() {
        if (receiver != null) {
            unregisterReceiver(receiver);
        }
        super.onDestroy();
    }
}
