#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2021-present, sun-shine cloud, Inc.
# All rights reserved
# video on demond to Stream (dts) 
# 根据请求的参数，来实时生成TS的内容，并返回给前端的播放器，整个时间需要在1秒内完成；
from trakData import trakData
from mp4Tools import mp4Tools
from PesPack import PesPack
import tsCRC32
import struct
import os
import logging_config

logger = logging_config.Config().get_config()

class tsPack():

    #获取的mp4片段的数据内容
    mp4data = None
    #对于文件的绝对偏移量；abs_soff 起始偏移量 abs_eoff终止偏移量；
    abs_soff = 0
    abs_eoff = 0
    pat_count = 0
    pmt_count = 0

    def __init__(self, mp4_md5, start, end):

        #根据mp4_md5获取redis中的数据,因为数组中保存的序号是从0开始的，起始与终止的点都包含在内进行计算，；
        self.pat_count = 0
        self.pmt_count = 0
        self.start = start
        self.end = end
        self.mp4_md5 = mp4_md5
        trakdata = trakData()
        #通过mp5获取原始mp4文件的url访问地址（redis)；
        self.url = trakdata.getMp4Url(mp4_md5)
        self._vtrak = None
        self._atrak = None
        self.tfile = str(self.mp4_md5)+"_"+str(start)
        #通过md5获取保存在redis中的mp4相关头数据信息
        self._vtrak, self._atrak = trakdata.getTrakData(mp4_md5)
        #初始化设置pes打包实例
        self.pes_pack = PesPack(self._vtrak.timescale, self._vtrak.sample_time_site, self._atrak.timescale, self._atrak.sample_time_site)
        return
        
    #根据video请求来的内容来生成mp4的文件偏移量，里面即有音频的内容出含有视频的内容；
    def getFileOffset(self):

        start_voff = 0
        end_voff = 0       
        #根据偏移量取得文件中的部分内容；
        start_voff = self._vtrak.sample_offset[self.start]
        total_samplenum = len(self._vtrak.sample_offset)

        if self.start >= total_samplenum - 1:
            end_voff = 999999999999999
        else:
            #因为start和end是包含start的起始位置和end终止位置的地方，所以end需要终止点的起始位置+终帧的size
            end_voff = self._vtrak.sample_offset[self.end]+ self._vtrak.sample_size[self.end]

        #上面是根据视频文件做的判断，还需要加进音频文件的偏离计算；这部分内容在后续增加进去；
        #######################################################################      
        a_start, a_end = self.pes_pack.getAudioRange(self.start, self.end)
        print("a_start:"+str(a_start)+" a_end:"+str(a_end))
        start_aoff = self._atrak.sample_offset[a_start]
        end_aoff = self._atrak.sample_offset[a_end] + self._atrak.sample_size[a_end]
        #######################################################################
        start_off = min(start_aoff, start_voff)
        end_off = max(end_aoff, end_voff)
        self.a_start = a_start
        self.a_end = a_end
        self.abs_offset = start_off
        return start_off, end_off

    #根据上面获取到的文件偏移量，来通过http的方式下载所需的内容片断，以获取mp4片段的数据内容；
    def getMp4Data(self):

        s_off, e_off = self.getFileOffset()
        tools = mp4Tools()

        self.mp4data = tools.down_Mp4Slice(self.url, self.mp4_md5, s_off, e_off)
        self.abs_soff = s_off
        self.abs_eoff = e_off

    #获取通过打包后生成的TS内容
    def getTS(self):
        #从远程服务器上下载相应的片段内容；
        self.getMp4Data()
        #获取到了原始文件中的相应数据内容；全部帧数据封装后的数组内容
        data_a = self.mk_TSPackages()
        ret_b = b''
        with open(self.tfile, "wb") as f:        
            for d in data_a:
                f.write(d)
        with open(self.tfile, "rb") as f1: 
            ret_b = f1.read()

        os.remove(self.tfile)
        return ret_b
    
    #获取视频帧数据,在取帧数据时，会不会有帧数据会分chunk的情况（看网上说的一帧只能在一个chunk内，但是不是这样目前还不确定，如果有的话，会有风险!!!）
    #取得帧的数据，并返回是否是关键帧和有sps_pps的内容；
    def getVideoFrameData(self, ifream):

        fill_c = [0x00, 0x00, 0x00, 0x01]
        #是否带sps和pps
        sps_pps_flag = False
        key_flag = False
        f_soff = self._vtrak.sample_offset[ifream]
        f_size = self._vtrak.sample_size[ifream]
        f_eoff = f_soff + f_size
        f_data = self.mp4data[f_soff-self.abs_soff:f_eoff-self.abs_soff]
        #因为提取的h264内容，前四个字节是代表长度，需要把长度的四个字节去掉，才能够提取到完整的帧数据；，不带SEI信息的内容，应该是计算出的长度与实际长度相等；
        a_fdat = f_data
        olen = len(a_fdat)
        o_len = a_fdat[:4]
        h_int = int.from_bytes(o_len, byteorder='big', signed=False)
        if o_len == h_int + 4:
            a_fdat = a_fdat[4:]
            a_fdat = bytes(fill_c) + a_fdat
            return a_fdat, key_flag, sps_pps_flag

        #如果判读出计算的长度与实际长度不相等，则可能会存在SEI或者其它的信息内容，下面需要去除SEI的内容，并且对于PPS或SPS的数据要进行保留，在增加视频帧的内容时需要在前面加0x000001
        sps = b""
        pps = b""

        while True:
            v_type = a_fdat[4] 
            v_len = a_fdat[:4]
            h_int1 = int.from_bytes(v_len, byteorder='big', signed=False)

            v_type1 = v_type&0x1F
            if h_int1 > len(a_fdat):
                a_fdat = f_data
                break
                # 1：非IDR图像中不采用数据划分的片段
                # 2：非IDR图像中A类数据划分片段
                # 3：非IDR图像中B类数据划分片段
                # 4：非IDR图像中C类数据划分片段
                # 5：IDR图像的片段
            #在此部分可能会提出出SPS和PPS的内容；
            if v_type1 == 0x07:
                sps = a_fdat[4:4+h_int1]

            if v_type1 == 0x08:
                pps = a_fdat[4:4+h_int1]

            if v_type1 in (0x01, 0x02, 0x03, 0x04, 0x05):
                a_fdat = a_fdat[4:]
                break
            a_fdat = a_fdat[h_int1+4:]

        #返回前需要判读是否有PPS或者SPS的内容，如果有的话，需要加到内容里面
        if len(pps) > 0:
            a_fdat = pps + bytes(fill_c) + a_fdat
            sps_pps_flag = True

        if len(sps) > 0:
            a_fdat = sps + bytes(fill_c) + a_fdat
            sps_pps_flag = True

        if v_type1 == 0x05:
            key_flag = True

        return a_fdat, key_flag, sps_pps_flag

    #获取音频帧数据；
    #音频封装的时候，一定需要加入ADTS头的内容，说明如下：
    # syncword              12b     固定为0xfff
    # id                    1b      0:mpeg-4, 1:mpeg-2
    # layer                 2b      00
    # protection_absent     1b      固定为1

    # profile               2b      0-3 1:aac
    # simple_index          4b      0:96000 1:882000 2:64000 3:48000 4:44100 5:32000 6:24000 7:22050 8:16000 9:12000 10:11025 11:8000 12:7350
    # private_bit           1b      0
    # channel_on            3b      1-4:channel
    # original-copy         1b      0
    # home                  1b      0
    # copyright-bit         1b      0
    # copyright-start       1b      0
    # aac_frame_length      13b     含ADTS的总长度
    # adts-fill             11b     固定为:0x7FF
    # number-of-raw-
    # data-black-inframe    2b      固定为00

    def getAudioFrameData(self, ifream):

        ADTS_0_15 = 0xFFF10000000000
        f_soff = self._atrak.sample_offset[ifream]
        f_size = self._atrak.sample_size[ifream]
        f_eoff = f_soff + f_size
        f_data = self.mp4data[f_soff-self.abs_soff:f_eoff-self.abs_soff]
        #音频的封装并没有其它的内容需要处理，只是提取相应的数据即可
        #打包aac⾳频必须加上⼀个adts(Audio Data Transport Stream)头
        #计算包的长度和后面的11位内容，共为3个字节，24位；
        a_len = f_size + 7
        b24 = (a_len<<11)|0x7FF
        #根据 trak.vscale来提取simple_index值, 默认48000
        sample_index = 3

        asdict = { "96000":0, "88200":1, "64000":2, "48000":3, "44100":4, "32000":5, "24000":6, "22050":7, "16000":8, "12000":9, "11025":10, "8000":11,"7350":12}
        a_sample = str(self._atrak.timescale)
        if a_sample in asdict:
            sample_index = asdict[a_sample]
        
        ADTS_16_17 = 0x4000000000
        ADTS_16_26 = (sample_index<<34) | 0x80000000
        ADTS_27_55 = b24<<2

        ADTS_ALL = ADTS_0_15|ADTS_16_17|ADTS_16_26|ADTS_27_55
        adts_head = ADTS_ALL.to_bytes(7, byteorder='big')
        
        ret_data = adts_head + f_data 
        return ret_data

    # #根据起始的帧和终止帧生成PES的数据内容；
    def mk_TSPackages(self):
        #根据帧数来生成TS的数据
        self.counter = 0
        ts_vall = []
        #在每一帧的视频帧被打包到pes的时候，其开头必定要加上 00 00 00 01 09 xx  这个nal。不然就有问题，这是苹果官网中的要求
        nau = [0x00, 0x00, 0x00, 0x01, 0x09, 0xf0]
        #nalu = [0x00, 0x00, 0x00, 0x01] 
        nalu = [0x00, 0x00, 0x01]

        #定义下面两个变量是为了后面计算音频的数据内容；
        f_vdts = 0
        e_vpts = 0
        
        #根据视频的起始和终止的帧，生成视频的帧数据列表
        for i in range(self.start, self.end + 1):
            #返回帧的原始数据
            f_data, key_flag, sps_pps_flag = self.getVideoFrameData(i)
            # self.printHex(f_data, 1024*1024)
            #把帧的原始数据进行ES打包
            # f_data1 = self.pes_pack.mkEsData(f_data)

            f_data1 = bytes(nalu) + f_data
            #如果是第一帧还需要加入SPS和PPS的信息,切割后的第一帧都为关键帧
            if i == self.start:
                f_data1 = bytes(nalu)+ self._vtrak.sps + bytes(nalu)+ self._vtrak.pps + bytes(nalu) + f_data
            #nalu = 帧数据+sps+pps, 如果打成PES包，还需要加上包头 pes = pes包头+nalu
            offset = self._vtrak.sample_decode_off[i]
            f_data1 = bytes(nau) + f_data1
            pes_data = self.pes_pack.mk_pesVData(i, offset, f_data1)
            #每个帧的头一个包中应含有PCR的内容， 取DTS做为PCR
            v_pts = self.pes_pack.getVideoPTS(i, offset)
            pcr = self.pes_pack.getDTS(i)
            v_dts = self.pes_pack.getVideoDTS1(i)

            if f_vdts == 0:
                f_vdts = pcr

            ts_f_data = self.ts_vpack(pes_data, pcr)
            ts_vall.append(ts_f_data)
            logger.debug("current video frame is :" + str(i) + " v_pts: "+ str(v_pts) + " v_dts: "+ str(v_dts) + " v_pcr: "+ str(pcr))

        if self.end < self._vtrak.sample_counts - 1:
            e_vdts = self.pes_pack.getDTS(self.end)
        else:
            e_vdts = 0x7FFFFFFF
        
        ts_aall = []
        self.counter = 0
        #根据音频的起始和终止的帧，生成音频的帧数据列表, a_start和a_end是音频的起始和终止点,对于音频来说组成的格式是：
        # 000001 iframe_len(帧长度2字节) 80 80（pts标志) 05（pts长度） pts(字节) + 音频内容
        # 下面要进行音频的封装的工作，因为音频可以把多个包打到一个packet中，所以设定每7个视频帧根着一个音频的帧，
        # 音频帧的pts不能够大于视频帧的pts，大了会出现声音不连续的情况；

        #设置在封包时多少个视频包后插一个音频包,初始设置是7个
        AV_NUM = 6

        #目前a_start和a_end基本是在获取内容时粗步定的一个范围，还需要根椐视频的数据来精细化数值(f_vpts, e_vpts)
        af_start = self.a_start
        af_end = self.a_end
        #范围判定在原则，起始点，如果当前点 i 的pts>f_vdts,则取 a_start = i -1
        #如果终止点i的pts > e_vdts, 则取a_end = i - 1
        for a_i in range(self.a_start, self.a_end):
            s_pts, a_pts = self.pes_pack.getAudioPTS(a_i)
            if a_i > self.a_start and a_pts > f_vdts and af_start == self.a_start:
                af_start = a_i
            if a_pts >= e_vdts and a_i >= self.a_start:
                af_end = a_i - 1
                break

        af_start = af_start - 4
        if af_start < 0:
            af_start = 0
        


        logger.debug("af_start: "+ str(af_start) + " af_end: "+ str(af_end))
        vframes  = []
        vgrp = []
        i  = 0

        for m in range(self.start, self.end + 1):
            i = i + 1
            vframes.append(m)
            if i ==  AV_NUM:
                vgrp.append(vframes)
                vframes = []
                i = 0

        if len(vframes) > 0:
            vgrp.append(vframes)

        au_data = []

        for frames in vgrp:
            au_data = []
            max_f = frames[len(frames) - 1 ]
            #取得本段视频的最大pts，音频内的pts都不能够大于这个pts的值
            max_pts = self.pes_pack.getVideoDTS1(max_f)

            au_data = b""

            for i in range(af_start, af_end):
                s_pts, a_pts = self.pes_pack.getAudioPTS(i)
                f_adata = self.getAudioFrameData(i)
                au_data = au_data + f_adata
                logger.debug("current audio frame is :" + str(i) + " a_pts: "+ str(a_pts))

                if a_pts > max_pts:
                    pes_adata = self.pes_pack.mk_pesAData(af_start, au_data)
                    ts_f_adata = self.ts_apack(pes_adata)
                    ts_aall.append(ts_f_adata)
                    au_data = b""
                    af_start = i + 1
                    break

            if len(au_data) > 0:
                pes_adata = self.pes_pack.mk_pesAData(af_start, au_data)
                ts_f_adata = self.ts_apack(pes_adata)
                ts_aall.append(ts_f_adata)          

        pat = self.getPAT()
        pmt = self.getPMT()

        #ts_all是返回的数据封装数组
        ts_all = []
        ts_all.append(bytes(pat))
        ts_all.append(bytes(pmt))        
        #以视频为主来生成最终的TS包，每7个视频后加一个音频的包内容；

        i = 0
        for vts in ts_vall:
            ts_all = ts_all + vts
            i = i + 1
            if i == AV_NUM:
                ts_all = ts_all + ts_aall[0]
                #再增加PAT和PMT的内容
                ts_all.append(bytes(pat))
                ts_all.append(bytes(pmt)) 
                ts_aall = ts_aall[1:]
                i = 0
        
        for ts_a in ts_aall:
            ts_all = ts_all + ts_a

        return ts_all
    
    #针对于pes_data数据进行TS的封包操作；TS包每个长度是188，所以需要把一帧的数据按TS的格式进行封装；ts_vpack是视频包的封装操作；
    def ts_vpack(self, pesdata, pcr):

        ret = []
        #一帧的数据的第一个包头；
        ts_head_first = [0x47, 0x41, 0x00]
        #一帧的数据的非第一个包头；
        ts_head_no_first = [0x47, 0x01, 0x00]
        #后面是自适应字段的封装，主要是PCR的封装，PCR设置为DTS的值；还有是为了为了传送打包后长度不足188B（包括包头）的不完整TS；
        #添加PCR的内容的包长度将增加7个字节， 所以如果pesdata的数据长度< 188-4-1-7则需要增加填充的长度；

        #第一个包一定是带有自适应的标记的，所以 0011，即0x30
        s_f = 0x30

        #下面再处理第一帧全部都设置为带PCR的内容，
        pcr_flag = 0x10
        #PCR字字段格式6B，48bit, PCR:33, reserved:6, original_program_clock_reference_extension:9
        pcr1 = ((0x000000000000|pcr)<<15)| 0x7E00
        # pcr_a = struct.pack("6b", pcr1)
        pcr_a = pcr1.to_bytes(6, byteorder='big')
        #做为填充字段，则需要设置一个PCR的标志位，长度后面+PCR的标志，所以一共有两个占位字节，如果有PCR则需要设置为0x10，如果没有则设置为0x00:
        #PCR的内容一共占6个字节（48位），加上一个字节表示PCR的标志位(pcr_flag=0x10),所以PCR的内容一共占7位；
        #因为默认都加了自填充字段，所以前面还需要有一位的自适应的长度字段（默认:0x07),所以最小的长度应该是pesdata的长度加上8位；
        #PCR的内容也是填充的内容，如果PES的长度加上PCR的长度也小于184则需要填充0xFF字节，可以尝试全部在第一帧进行填充

        adaptation_field_length = 0x07
        fill_data = []
        ts_d = []
        #先判读数据的长度是否需要填充，TS包长度为188，前四个字节是每个TS的包头，所以实际的数据区只有184，因为第一包的里面含有PCR的内容，2位+6位（PCR）
        # 所以 如果长度< =176，则需要填充；
        if len(pesdata) <= 176:
            fill_num = 176 - len(pesdata)
            adaptation_field_length1 = adaptation_field_length  + fill_num
            a_fill = []
            for i in range(0, fill_num):
                a_fill.append(0xFF)
            pesdata = bytes(a_fill)+pesdata
            s_f = 0x30
            s_c = self.counter&0x0F
            s_fc = s_f|s_c
            ts_p = bytes(ts_head_first) + s_fc.to_bytes(1, byteorder='big') + adaptation_field_length1.to_bytes(1, byteorder='big') + pcr_flag.to_bytes(1, byteorder='big') + pcr_a + pesdata
            self.counter = self.counter + 1
            if self.counter > 15:
                self.counter = 0
            ts_d.append(ts_p)
            return ts_d

        #以后的内容都是在多包的情况进行处理，第一个包的内容应该是含有PCR的数据内容，所以应该是188 = 4+8(PCR)+ 176(部分PES)，可以把PCR的内容直接加到pesdata上
        pesdata1 = adaptation_field_length.to_bytes(1, byteorder='big') + pcr_flag.to_bytes(1, byteorder='big') + pcr_a + pesdata
        n_num = len(pesdata1) % 184
        #如果n_num有余数，则说明可能需要进行填充，如果余数为183，则可以通过一个调节字来完成
        fill_num = 0
        have_pcr = True

        if n_num == 183:
            pesdata1 = pesdata
            have_pcr = False
      
        r_num = int((len(pesdata1) + 183)/184)

        t_len = len(pesdata1)
        isFirst = True
        for i in range(0, r_num):
            s_f = 0x10
            ts_head = ts_head_no_first            
            if isFirst:
                #第一个包内，默认是含有自适应内容，所以标志为0x30，但如果no_pcr = True,则为0x10
                if have_pcr:
                    s_f = 0x30
                ts_head = ts_head_first
                isFirst = False

            pes_s = pesdata1[i*184:]
            if len(pesdata1) > 184:
                pes_s = pes_s[0:184]
            if len(pes_s) < 184:
                s_f = 0x30
                m = 184 - len(pes_s)
                f_f = [0x00,]
                for mi in range(2, m):
                    f_f.append(0xFF)
                f_len = len(f_f)
                pes_s = f_len.to_bytes(1, byteorder='big') + bytes(f_f) + pes_s

            s_c = self.counter&0x0F
            s_fc = s_f|s_c

            ts_p = bytes(ts_head) + s_fc.to_bytes(1, byteorder='big') + pes_s

            ts_d.append(ts_p)
            self.counter = self.counter + 1
            if self.counter > 15:
                self.counter = 0

        return ts_d


    #针对于pes_data的音频数据进行TS的封包操作；TS包每个长度是188，所以需要把一帧的数据按TS的格式进行封装
    def ts_apack(self, pesdata):

        ret = []
        #一帧的数据的第一个包头；
        ts_head_first = [0x47, 0x41, 0x01]
        #一帧的数据的非第一个包头；
        ts_head_no_first = [0x47, 0x01, 0x01]
        #后面是自适应字段的封装，如果第一个包的长度小于188-4-2，则需要进行填充0xFF；

        #第一个包一定是带有自适应的标记的，所以 0011，即0x30
        s_f = 0x30

        #下面再处理第一帧设置为不带PCR内容，因为音频不需加PCR的内容，0x50为含PCR，0
        pcr_flag = 0x40
        #缺省的长度是0x01
        adaptation_field_length = 0x01
        fill_data = []
        ts_d = []
        # 所以 如果长度< =182，则需要填充；
        if len(pesdata) <= 182:
            fill_num = 182 - len(pesdata)
            adaptation_field_length1 = adaptation_field_length  + fill_num
            a_fill = []
            for i in range(0, fill_num):
                a_fill.append(0xFF)
            pesdata = bytes(a_fill)+pesdata
            s_f = 0x30
            s_c = self.counter&0x0F
            s_fc = s_f|s_c
            ts_p = bytes(ts_head_first) + s_fc.to_bytes(1, byteorder='big') + adaptation_field_length1.to_bytes(1, byteorder='big') + pcr_flag.to_bytes(1, byteorder='big') + pesdata
            self.counter = self.counter + 1
            if self.counter > 15:
                self.counter = 0
            ts_d.append(ts_p)
            return ts_d

        #以后的内容都是在多包的情况进行处理，第一个包的内容应该是含有PCR的标志位数据内容，所以应该是188 = 4+2+ 182(部分PES)，
        pesdata1 = adaptation_field_length.to_bytes(1, byteorder='big') + pcr_flag.to_bytes(1, byteorder='big') + pesdata
        n_num = len(pesdata1) % 184
        #如果n_num有余数，则说明可能需要进行填充，如果余数为183，则可以通过一个调节字来完成
        fill_num = 0
        have_pcr = True

        if n_num == 183:
            pesdata1 = pesdata
            have_pcr = False
      
        r_num = int((len(pesdata1) + 183)/184)

        t_len = len(pesdata1)
        isFirst = True
        for i in range(0, r_num):
            s_f = 0x10
            ts_head = ts_head_no_first            
            if isFirst:
                #第一个包内，默认是含有自适应内容，所以标志为0x30，但如果no_pcr = True,则为0x10
                if have_pcr:
                    s_f = 0x30
                ts_head = ts_head_first
                isFirst = False

            pes_s = pesdata1[i*184:]
            if len(pesdata1) > 184:
                pes_s = pes_s[0:184]
            if len(pes_s) < 184:
                s_f = 0x30
                m = 184 - len(pes_s)
                f_f = [0x00,]
                for mi in range(2, m):
                    f_f.append(0xFF)
                f_len = len(f_f)
                pes_s = f_len.to_bytes(1, byteorder='big') + bytes(f_f) + pes_s

            s_c = self.counter&0x0F
            s_fc = s_f|s_c

            ts_p = bytes(ts_head) + s_fc.to_bytes(1, byteorder='big') + pes_s

            ts_d.append(ts_p)
            self.counter = self.counter + 1
            if self.counter > 15:
                self.counter = 0

        return ts_d


    #因为只是做协议转换，所以program_number都设置为0x0001; 每个节目号中只有一个节目内容program_map_PID = 0x0001
    def getPAT(self):
       
       #47 60 00 10 00 00 B0 0D 00 00 C1 00 00 00 01 F0 00 2A B1 04 B2
    #    #package-id = 0x0000表示这是PAT表
    #     pat_head = [0x47, 0x60, 0x00, 0x10, 0x00]

    #     #设定section_length = 13,因为PAT的长度固定是13
    #     pat_data1 = [0x00, 0xb0, 0x0d]
    #     pat_data2 = [0x00, 0x00, 0xc1, 0x00, 0x00]
    #     #program_number = 0x0001(1) program_map_PID = 0x1000(4096)
    #     pat_data3 = [0x00, 0x01, 0xF0, 0x00]
    #     o_c = pat_data1 + pat_data2 + pat_data3
    #     crc = list(tsCRC32.CRC32(o_c).to_bytes(4, "big", signed=False))
    #     #每个TS的Package的长度是188个字节，所以需要整理成188个字节的list
    #     pat_d = pat_head + o_c + crc
    #     for item in pat_d:
    #         print("0x%X,"%item, end=' ')
    #   pid = 1 0000 0000 0000        
        pat_d = [0x47, 0x40, 0x00] 
        #pid=0x0000 表示这是一个PAT
        pat_d1 = [0x00, 0x00, 
        0xB0, 0x0D, 0x00, 0x01, 0xC1, 0x00, 0x00, 
        0x00, 0x01,
        #表示这个PID= 1 0000 0000 0000 
        0xF0, 0x00, 
        0x2A, 0xB1, 0x04, 0xB2]
        pat_1 = 0x10|self.pat_count

        self.pat_count = self.pat_count + 1
        if self.pat_count > 15:
            self.pat_count = 0

        pat_d = pat_d + [pat_1,] + pat_d1    
        plen = len(pat_d)
        for i in range(plen, 188):
            pat_d.append(0xFF)           
        return pat_d

    #因为只是做协议转换，所以program_number都设置为0x0001; 每个节目号中只有一个节目内容program_map_PID = 0x0001
    def getPMT(self):

        # #47 60 81 10 00 02 B0 17 00 01 C1 00 00 E8 10 F0 00 1B E8 10 F0 00 03 E8 14 F0 00 66 74 A4 2D
        # #package-id = 0x81表示这是PMT表，该值在PAT中指定
        # pmt_head = [0x47, 0x60, 0x81, 0x10, 0x00] 
        # #length = 0x0d是指示本段向下的长度（含CRC）
        # pmt_data1 = [0x02, 0xB0, 0x17]
        # #program_number = 0x0001, 指出该节目对应于可应用的Program map PID与上面对应, #reserved(0xF) and program_info_length = 0(0x000)
        # pmt_data2 = [0x00, 0x01, 0xc1, 0x00, 0x00, 0xE8, 0x10, 0xF0, 0x00]
        # #第一个字节为stream_type = 0x1B是视频类型，PID=0x810,， 指定视频的包PID=0x810
        # pmt_data3 = [0x1B, 0xE8, 0x10, 0xF0, 0x00]
        # #第一个字节为stream_type = 0x03是视频类型，PID=0x814,指定视频的包PID=0x814
        # pmt_data4 = [0x03, 0xE8, 0x14, 0xF0, 0x00]

        # o_c = pmt_data1 + pmt_data2 + pmt_data3 + pmt_data4 
        # crc = list(tsCRC32.CRC32(o_c).to_bytes(4, "big", signed=False))
        # #每个TS的Package的长度是188个字节，所以需要整理成188个字节的list
        # pmt_d = pmt_head + o_c + crc
    #   pid = 1 0000 0000 0000 
        pmt_d = [0x47, 0x50, 0x00]          
        pmt_d1 =[0x00, 0x02,
                #长度是1D  
                0xB0, 0x1D, 
                0x00, 0x01, 
                0xC1, 0x00,
                0x00, 0xE1, 
                0x00, 0xF0, 0x00, 
                0x1B, 0xE1, 
                0x00, 0xF0, 
                0x00, 0x0F, 
                #流类型0xE1，代表视频，
                0xE1, 0x01, 0xF0, 0x06, 0x0A, 
                0x04, 0x75, 0x6E, 0x64, 0x00, 
                0x08, 0x7D, 0xE8, 0x77]
    
        pmt_1 = 0x10|self.pmt_count

        self.pmt_count = self.pmt_count + 1
        if self.pmt_count > 15:
            self.pmt_count = 0

        pmt_d = pmt_d+ [pmt_1,] + pmt_d1               
        # for item in pmt_d:
        #     print("0x%X,"%item, end=' ')         
        plen = len(pmt_d)
        for i in range(plen, 188):
            pmt_d.append(0xFF)
        # print("")       
        return pmt_d

    def printHex(self, b, vnum):
        i = 0
        for item in b:
            i = i + 1
            print("0x%02X,"%item, end=' ') 
            if i > vnum:
                break
