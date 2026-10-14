/* Appended to the production model adapter, not a second IIS implementation. */
int main(int argc,char **argv) {
    if(argc!=2)return 2;
    Clock c={12288000};QEMUTimer timer={.expire_time=-1};
    P2DMedia s={.pclk=&c,.event=&timer};active_media=&s;
    s.audio=p2d_audio_open(argv[1]);if(!s.audio)return 3;s.output_enabled=true;
    iis_write(&s,4,0xa9,4);iis_write(&s,12,0x2000,4);iis_write(&s,0,1,4);
    int16_t values[]={32767,-32768,123,-456};
    for(unsigned i=0;i<4;i++)iis_write(&s,16,(uint16_t)values[i],2);
    drain(&s,s.serial_period*4,false);media_output_flush(&s);
    if(s.output_rate!=48000 || s.level || reads || irq_count)return 4;
    /* Consume left, mute across right+left, regain across right: no swapped pair. */
    iis_write(&s,16,11,2);drain(&s,clock_now+s.serial_period,false);
    s.output_enabled=false;media_output_boundary(&s,false);
    iis_write(&s,16,22,2);iis_write(&s,16,33,2);drain(&s,clock_now+s.serial_period*2,false);
    s.output_enabled=true;media_output_boundary(&s,false);
    iis_write(&s,16,44,2);iis_write(&s,16,55,2);iis_write(&s,16,66,2);
    drain(&s,clock_now+s.serial_period*3,false);media_output_flush(&s);
    /* Change clock after due work; output rate follows actual clock. */
    c.hz=11289600;media_clock(&s,0);if(s.output_rate!=44100)return 5;
    iis_write(&s,16,77,2);iis_write(&s,16,88,2);drain(&s,clock_now+s.serial_period*2,false);media_output_flush(&s);
    p2d_audio_close(s.audio);return 0;
}
