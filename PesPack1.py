#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2021-present, sun-shine cloud, Inc.
# All rights reserved.
# 获取到音频和视频资源后进行TS的封包操作；
# 需要校对时间戳信息，视帧的采样率、刻度；音频的采样率和刻度；


import datetime
import os.path
import struct
import sys
import time
import requests
from trackClass import trackClass
from hashlib import md5
import urllib.request
import struct
import tsCRC32

class PesPack():
    
    # vdata是视频帧的数据, vscale是视频采样率，vdetas是视频的刻度， 
    # adata是视频帧的数据, ascale是音频采样率，adetas是音频的刻度;
    def __init__(self, vscale, vdeltas, ascale, adeltas):

        self.vscale = vscale
        self.vdeltas = vdeltas
        self.ascale = ascale
        self.adeltas = adeltas

    # # sync_byte	                    8bit	同步字节，固定为0x47
    # # transport_error_indicator	    1bit	传输错误指示符，表明在ts头的adapt域后由一个无用字节，通常都为0，这个字节算在adapt域长度内
    # # payload_unit_start_indicator	1bit	负载单元起始标示符，一个完整的数据包开始时标记为1
    # # transport_priority	        1bit	传输优先级，0为低优先级，1为高优先级，通常取0
    # # pid	                        13bit	pid值
    # # transport_scrambling_control	2bit	传输加扰控制，00表示未加密
    # # adaptation_field_control	    2bit	是否包含自适应区，‘00’保留；‘01’为无自适应域，仅含有效负载；‘10’为仅含自适应域，无有效负载；‘11’为同时带有自适应域和有效负载。
    # # continuity_counter	        4bit	递增计数器，从0-f，起始值不一定取0，但必须是连续的                
        
        self.continuity_counter = None
        #每位代表的含义是：0x47, 0 1 0 pid=0 1000 0001 0000, 00 11(自适应区+有效负荷) counter=0001
        self.ts_vhead = [0x47, 0x48, 0x10]
        #自适应字段长度是7，包含PCR值，每帧的PCR值可以取DTS的值；
        self.ts_adaptation = [0x07, 0x50]
        #每位代表的含义是：0x47, 0 1 0 pid=0 1000 0001 0100, 00 11 counter=0001        
        self.ts_ahead = [0x47, 0x48, 0x14, 0x31]

    #     # pes start code	3Byte	开始码，固定为0x000001
    #     # stream id	1Byte	音频取值（0xc0-0xdf），通常为0xc0 视频取值（0xe0-0xef），通常为0xe0
    #     # pes packet length	2Byte	后面pes数据的长度，0表示长度不限制，只有视频数据长度会超过0xffff
    #     # flag	1Byte	通常取值0x80，表示数据不加密、无优先级、备份的数据
    #     # flag	1Byte	取值0x80表示只含有pts，取值0xc0表示含有pts和dts
    #     # pes data length	1Byte	后面数据的长度，取值5或10
    #     # pts	5Byte	33bit值
    #     # dts	5Byte	33bit值
        self.pes_head = [0x00, 0x00, 0x00, 0x01]
        self.pes_vstreamid = 0xe0
        self.pes_packet_length = 0x0000
        self.pes_flag = 0x80
        self.pes_ptsdts_flag = 0xC0
        self.pes_data_length = 0x0A

    #####################################################
    # pts：显示时间戳，单位是毫秒*90
    # dts：解码时间戳，单位是毫秒*90
    # pcr：节目时钟参考，单位是毫秒*90*300
    #####################################################

    # TS的基本知识：ts文件分为三次：ts层(Transport Stream)、pes层(Packet Elemental Stream)、es层(Elementary Stream)。
    # es层就是音视频数据，
    # pes层是在音视频数据上加了时间戳等数据帧的说明信息，
    # ts层是在pes层上加入了数据流识别和传输的必要信息。

    # TS层:ts包(Packet)大小固定为188字节，
    # ts层分为三个部分：ts header、adaptation field、payload。ts header固定4个字节；
    # adaptation field可能存在也可能不存在，主要作用是给不足188字节的数据做填充；payload是pes数据。

    # ts层的内容是通过PID值来标识的，主要内容包括：PAT表、PMT表、音频流、视频流。
    # 解析ts流要先找到PAT表，只要找到PAT就可以找到PMT，然后就可以找到音视频流了。
    # PAT表的PID值固定为0。
    # PAT表：他主要的作用就是指明了PMT表的PID值。
    # PMT表：他主要的作用就是指明了音视频流的PID值。
    # 音频流/视频流：承载音视频内容。

    #因为只是做协议转换，所以program_number都设置为0x0001; 每个节目号中只有一个节目内容program_map_PID = 0x0001
    def getPAT(self):
       
       #47 60 00 10 00 00 B0 0D 00 00 C1 00 00 00 01 E0 81 0C 8C BE 32
       #package-id = 0x0000表示这是PAT表
        pat_head = [0x47, 0x60, 0x00, 0x10, 0x00]

        #设定section_length = 13,因为PAT的长度固定是13
        pat_data1 = [0x00, 0xb0, 0x0d]
        pat_data2 = [0x00, 0x00, 0xc1, 0x00, 0x00]
        #program_number = 0x0001(1) program_map_PID = 0x0081(129),指定的PMT的PID为0x81
        pat_data3 = [0x00, 0x01, 0xe0, 0x81]
        o_c = pat_data1 + pat_data2 + pat_data3
        crc = list(tsCRC32.CRC32(o_c).to_bytes(4, "big", signed=False))
        #每个TS的Package的长度是188个字节，所以需要整理成188个字节的list
        pat_d = pat_head + o_c + crc
        for item in pat_d:
            print("0x%X,"%item, end=' ')
        print("")        
        plen = len(pat_d)
        for i in range(plen, 188):
            pat_d.append(0xFF)           
        return pat_d

    #因为只是做协议转换，所以program_number都设置为0x0001; 每个节目号中只有一个节目内容program_map_PID = 0x0001
    def getPMT(self):

        #47 60 81 10 00 02 B0 17 00 01 C1 00 00 E8 10 F0 00 1B E8 10 F0 00 03 E8 14 F0 00 66 74 A4 2D
        #package-id = 0x81表示这是PMT表，该值在PAT中指定
        pmt_head = [0x47, 0x60, 0x81, 0x10, 0x00] 
        #length = 0x0d是指示本段向下的长度（含CRC）
        pmt_data1 = [0x02, 0xB0, 0x17]
        #program_number = 0x0001, 指出该节目对应于可应用的Program map PID与上面对应, #reserved(0xF) and program_info_length = 0(0x000)
        pmt_data2 = [0x00, 0x01, 0xc1, 0x00, 0x00, 0xE8, 0x10, 0xF0, 0x00]
        #第一个字节为stream_type = 0x1B是视频类型，PID=0x810,， 指定视频的包PID=0x810
        pmt_data3 = [0x1B, 0xE8, 0x10, 0xF0, 0x00]
        #第一个字节为stream_type = 0x03是视频类型，PID=0x814,指定视频的包PID=0x814
        pmt_data4 = [0x03, 0xE8, 0x14, 0xF0, 0x00]

        o_c = pmt_data1 + pmt_data2 + pmt_data3 + pmt_data4 
        crc = list(tsCRC32.CRC32(o_c).to_bytes(4, "big", signed=False))
        #每个TS的Package的长度是188个字节，所以需要整理成188个字节的list
        pmt_d = pmt_head + o_c + crc
        for item in pmt_d:
            print("0x%X,"%item, end=' ')         
        plen = len(pmt_d)
        for i in range(plen, 188):
            pmt_d.append(0xFF)
        print("")       
        return pmt_d

    #根据帧数据进行TS的封包, ifnum是帧的序号， vdata是帧的h264压缩后的数据；
    def vpack(self, ifnum):
        #对于视频来说，每一帧前面都需要设置PCR值
        vdata = self.vdetas[ifnum]
        vlen = len(vdata) + 4
        #因为祼数据中没有增加valu的识别信息，所以需要在每帧的长度增加4个字节(0x00 0x00 0x00 0x01)
        ts_p = []
        ts_p = self.ts_vhead + self.getCounter


    def getCounter(self):
        if self.continuity_counter == None:
            self.continuity_counter = 0
        else:
            self.continuity_counter = self.continuity_counter + 1

        if self.continuity_counter > 15:
            self.continuity_counter = 0

        return struct.pack("B", self.continuity_counter)|0x30

    #在打包过程中需要把整型的pts或dts数值转换成5个字节的数组，并分为三个部分；‘0010’ PTS[32..30] marker_bit PTS[29..15] marker_bit PTS[14..0] marker_bit
    def ptsdts_fmt(self, p):
        ca = p
        fm1 = (ca&0x0000007FFF)<<1
        fm2 = (ca&0x003FFF8000)<<2
        fm3 = (ca&0x01C0000000)<<3
        fm4 = 0x2100010001
        pfmt = fm4|fm3|fm2|fm1
        return pfmt

    #计算每一帧视频的DTS(PCR相同与DTR相同)
    def getVideoDTSPTS(self, iframe, offset):
        #PCR是节目时钟参考，也是一种音视频同步的时钟，pcr、dts、pts 都是对同⼀个系统时钟的采样值，pcr 是递增的，因此可以将其设置为 dts 值,
        # ⾳频数据不需要 pcr(PCR的pid，一般与视频的pid是同一个值)。打包 ts 流时 PAT 和 PMT 表(属于文本数据)是没有 adaptation field，
        # 视频流和⾳频流都需要加 adaptation field
        # 音视频数据需要adaptation field。一般在⼀个帧的第⼀个 ts包和最后⼀个 ts 包⾥加adaptation field
        #音频的每帧的时间刻度
        b_time = 1
        f_timescale = self.vscale
        f_detas = self.vdetas
        video_frame_rate = f_timescale / f_detas
        f_dts = b_time + iframe*(90000 / video_frame_rate)
        #
        f_pts = b_time + f_dts + (90000 / video_frame_rate) * (offset/f_detas)
        return f_dts, f_pts

    # #计算每一帧音频的DTS(PCR相同)
    # def getAudioDTSPTS(self, iframe, offset):
    #     #PCR是节目时钟参考，也是一种音视频同步的时钟，pcr、dts、pts 都是对同⼀个系统时钟的采样值，pcr 是递增的，因此可以将其设置为 dts 值,
    #     # ⾳频数据不需要 pcr(PCR的pid，一般与视频的pid是同一个值)。打包 ts 流时 PAT 和 PMT 表(属于文本数据)是没有 adaptation field，
    #     # 视频流和⾳频流都需要加 adaptation field
    #     # 音视频数据需要adaptation field。一般在⼀个帧的第⼀个 ts包和最后⼀个 ts 包⾥加adaptation field
    #     #音频的每帧的时间刻度


    # #根据视频的PTS来获取音频的帧的内容；会返回二个列表：音频帧和DTS
    # def getAudioDTSList(self, f_dts):
    #     #dts = 初始值 + (90000 * 48000) / audio_sample_rate = 1024，
    #     # audio_samples_per_frame这个值与编解码相关，aac取值1024，mp3取值1158，audio_sample_rate是采样率，比如24000、41000。AAC一帧解码出来是每声道1024个sample，也就是说一帧的时长为1024/sample_rate秒。所以每一帧时间戳依次0，1024/sample_rate，...，1024*n/sample_rate秒。
    #     #根据f_dts来计算起始的音频帧内空；
    #     b_time = 1
    #     f_dts = f_dts - b_time
    #     f_timescale = self.ascale
    #     f_detas = self.adetas        
    #     #开始音频帧
    #     audio_sample_rate = f_timescale / f_detas
    #     b_an = (f_dts /(90000*self.vscale)) * audio_sample_rate
    #     #每帧图片对应的音频的帧数
    #     t_an = self.vdetas/self.vdetas/(audio_sample_rate/self.vscale)
    #     a_iarray = []
    #     a_pts = []

    #     for i in range(0, t_an):
    #         a_iarray = self.adata[int(b_an)+i]
    #         apts = f_dts + i*(90000 * self.ascale) / audio_sample_rate
    #         a_pts.append[apts]

    #     return a_iarray, a_pts
        
if __name__ == '__main__':

    pes = PesPack()
    start = datetime.datetime.now()
    # ts.getPAT()
    # ts.getPMT()
    pes.ptsdts_fmt(19203)
    pes.vpack(123)    
    # metad.mkM3u8()         
    end = datetime.datetime.now()     
    print(str(end-start)+" 秒")
