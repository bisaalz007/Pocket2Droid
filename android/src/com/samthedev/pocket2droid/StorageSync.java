package com.samthedev.pocket2droid;
import java.io.FileDescriptor;
import java.io.IOException;

final class StorageSync {
    static void flush(FileDescriptor fd) throws IOException { fd.sync(); }
}
