package com.samthedev.pocket2droid;
/** Streaming linear stereo interpolation; fixed caller-owned storage. */
final class PcmResampler {
    private int source,output,left,right;private long index,next;
    void configure(int sourceRate,int outputRate){source=sourceRate;output=outputRate;index=0;next=0;}
    int process(short[] in,int offset,int frames,short[] out,int capacityFrames) {
        if(source<=0||output<=0||frames<0||offset<0||offset+frames*2>in.length)throw new IllegalArgumentException("Resampler input");
        int count=0;
        for(int i=0;i<frames;i++,index++) {
            int l=in[offset+i*2],r=in[offset+i*2+1];long current=index*output;
            while(next<=current) {
                if(count>=capacityFrames||count*2+1>=out.length)throw new IllegalArgumentException("Resampler output capacity");
                long fraction=index==0?output:next-(index-1)*output;
                out[count*2]=(short)(left+((long)(l-left)*fraction)/output);
                out[count*2+1]=(short)(right+((long)(r-right)*fraction)/output);
                next+=source;count++;
            }
            left=l;right=r;
        }
        return count;
    }
}
