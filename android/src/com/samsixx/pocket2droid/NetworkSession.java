package com.samsixx.pocket2droid;
import android.content.Context;
import android.net.*;
import java.io.*;
import java.net.InetAddress;
import java.util.*;
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;

/** One observer/private DNS file per engine; late callbacks cannot reuse a path. */
final class NetworkSession implements AutoCloseable {
    interface Status {void changed(String text);}
    interface Source {
        List<InetAddress> current()throws Exception;
        void register(Runnable changed)throws Exception;
        void unregister();
    }
    private final Source source;private final Executor worker;private final Status status;
    private final File resolver;private boolean active,registered,closed;private long generation;
    private byte[] published;
    NetworkSession(Context context,File privateRoot,Executor worker,Status status){this(new AndroidSource(context),privateRoot,worker,status);}
    NetworkSession(Source source,File privateRoot,Executor worker,Status status){
        this.source=source;this.worker=worker;this.status=status;
        resolver=new File(privateRoot,"dns-"+UUID.randomUUID().toString()+".conf");
    }
    File resolverFile(){return resolver;}
    synchronized void start()throws IOException {
        if(closed)throw new IOException("Network session is already closed");
        if(active)return;
        active=true;generation++;
        try {
            NetworkConfig.publishResolver(resolver,new byte[0]);published=new byte[0];
            registered=true;source.register(this::changed);
            refresh(generation);
        } catch(Exception e){close();throw new IOException("Cannot prepare Internet access: "+e.getMessage(),e);}
    }
    private void changed(){
        final long token;synchronized(this){if(!active)return;token=generation;}
        try{worker.execute(()->{synchronized(NetworkSession.this){if(!active||token!=generation)return;try{refresh(token);}catch(Exception e){status.changed("Internet DNS unavailable: "+e.getMessage());}}});}
        catch(RejectedExecutionException retired){/* A closing engine owns cleanup. */}
    }
    private void refresh(long token)throws Exception {
        if(!active||token!=generation)return;
        byte[] bytes=NetworkConfig.resolverBytes(source.current());
        if(!Arrays.equals(bytes,published)){NetworkConfig.publishResolver(resolver,bytes);published=bytes;}
        status.changed(bytes.length==0?"Internet access enabled; waiting for network DNS":"Internet access enabled");
    }
    @Override public synchronized void close(){
        if(closed)return;closed=true;active=false;generation++;
        if(registered){registered=false;try{source.unregister();}catch(RuntimeException ignored){}}
        resolver.delete();
    }
    private static final class AndroidSource implements Source {
        private final ConnectivityManager manager;private ConnectivityManager.NetworkCallback callback;
        AndroidSource(Context context){manager=(ConnectivityManager)context.getSystemService(Context.CONNECTIVITY_SERVICE);}
        public List<InetAddress> current(){
            if(manager==null)return Collections.emptyList();
            Network network=manager.getActiveNetwork();LinkProperties link=network==null?null:manager.getLinkProperties(network);
            return link==null?Collections.emptyList():link.getDnsServers();
        }
        public void register(Runnable changed)throws IOException {
            if(manager==null)throw new IOException("Android connectivity service unavailable");
            callback=new ConnectivityManager.NetworkCallback(){
                @Override public void onAvailable(Network network){changed.run();}
                @Override public void onLinkPropertiesChanged(Network network,LinkProperties properties){changed.run();}
                @Override public void onLost(Network network){changed.run();}
            };
            manager.registerDefaultNetworkCallback(callback);
        }
        public void unregister(){if(manager!=null&&callback!=null){manager.unregisterNetworkCallback(callback);callback=null;}}
    }
}
