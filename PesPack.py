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
from trakClass import trakClass
from hashlib import md5
import urllib.request
import struct
import tsCRC32

class PesPack():
    
    # vdata是视频帧的数据, vscale是视频采样率，vdetas是视频的刻度， 
    # adata是视频帧的数据, ascale是音频采样率，adetas是音频的刻度;
    # voffset是视频的解码的时间差，aoffset是音频的解码时间差
    def __init__(self, vscale, vdeltas, ascale, adeltas):

        self.vscale = vscale
        self.vdeltas = vdeltas
        self.ascale = ascale
        self.adeltas = adeltas
    #下面是关于PES的相关说明：
    #     # pes start code	3Byte	开始码，固定为0x000001
    #     # stream id	1Byte	音频取值（0xc0-0xdf），通常为0xc0 视频取值（0xe0-0xef），通常为0xe0
    #     # pes packet length	2Byte	后面pes数据的长度，0表示长度不限制，只有视频数据长度会超过0xffff
    #     # flag	1Byte	通常取值0x80，表示数据不加密、无优先级、备份的数据
    #     # flag	1Byte	取值0x80表示只含有pts，取值0xc0表示含有pts和dts
    #     # pes data length	1Byte	后面数据的长度，取值5或10
    #     # pts	5Byte	33bit值
    #     # dts	5Byte	33bit值
        self.pes_vstart_code = [0x00, 0x00, 0x01, 0xe0]
        self.pes_astart_code = [0x00, 0x00, 0x01, 0xc0]        
        # #视频流的ID设为 0xe0,H264
        # self.pes_vstream_id = 0xe0
        # #音频的ID设为 0xc0，AAC
        # self.pes_astream_id = 0xc0        
        #pes_packet_length的长度，需要整合数据后进行计算,es数据的长度+剩余ps报头长(13)
        self.pes_packet_length = 0x0000
        #flag的标志，是表示数据不加密，无优先级:0x80
        #pts dts标志:数据含有pts和dtd: 0xc0
        #pes含有的pts和dts的长度，因为即含有pts又有dts，所以两个加一起是10个字节的长度:0x0A
        self.pes_pts_dts_flag = [0x80, 0xC0, 0x0A]

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

    #根据帧数据进行TS的封包, iframe是帧的序号， vdata是帧的h264压缩后的数据；
    def mk_pesData(self, iframe, offset, vdata):
        #nalu = 帧数据+sps+pps, 如果打成PES包，还需要加上包头 pes = pes包头+nalu
        dts, pts = self.getVideoDTSPTS(iframe, offset)
        #pes的长度为 5(pts.len)+5(dts.len)+3+vdata.len
        pes_length = len(vdata)+13
        # pes_packet_length = struct.pack('H',pes_length)
        pes_packet_length = struct.pack('H',0)        
        pes_data = bytes(self.pes_vstart_code) + pes_packet_length + bytes(self.pes_pts_dts_flag) + pts + dts + vdata
        return pes_data

    # #根据vdata的帧数据内容生成NALU的数据， 主要是前端增加0x00000001;
    # def mkEsData(self, vdata):
    #     i_head = struct.pack('3x1b',1)
    #     f_esData = None
    #     f_esData = i_head + vdata
    #     return f_esData

    #在打包过程中需要把整型的pts或dts数值转换成5个字节的数组，并分为三个部分；‘0010’ PTS[32..30] marker_bit PTS[29..15] marker_bit PTS[14..0] marker_bit
    def pts_fmt(self, p):
        #PTS的起始码为0011，DTS的起始码为0001
        ca = p
        fm1 = (ca&0x0000007FFF)<<1
        fm2 = (ca&0x003FFF8000)<<2
        fm3 = (ca&0x01C0000000)<<3
        fm4 = 0x3100010001       
        pfmt = fm4|fm3|fm2|fm1
        # pfmt_a = struct.pack('b',pfmt)
        pfmt_a = pfmt.to_bytes(5, byteorder='big')
        l = [hex(int(i)) for i in pfmt_a]
        print(" ".join(l))
        return pfmt_a

    #在打包过程中需要把整型的pts或dts数值转换成5个字节的数组，并分为三个部分；‘0010’ PTS[32..30] marker_bit PTS[29..15] marker_bit PTS[14..0] marker_bit
    def dts_fmt(self, p):
        #PTS的起始码为0011，DTS的起始码为0001
        ca = p
        fm1 = (ca&0x0000007FFF)<<1
        fm2 = (ca&0x003FFF8000)<<2
        fm3 = (ca&0x01C0000000)<<3
        fm4 = 0x1100010001        
        pfmt = fm4|fm3|fm2|fm1
        # pfmt_a = struct.pack('b',pfmt)
        pfmt_a = pfmt.to_bytes(5, byteorder='big')      
        return pfmt_a


    #计算每一帧视频的DTS(PCR相同与DTR相同)
    def getVideoDTSPTS(self, iframe, offset):
        #PCR是节目时钟参考，也是一种音视频同步的时钟，pcr、dts、pts 都是对同⼀个系统时钟的采样值，pcr 是递增的，因此可以将其设置为 dts 值,
        # ⾳频数据不需要 pcr(PCR的pid，一般与视频的pid是同一个值)。打包 ts 流时 PAT 和 PMT 表(属于文本数据)是没有 adaptation field，
        # 视频流和⾳频流都需要加 adaptation field
        # 音视频数据需要adaptation field。一般在⼀个帧的第⼀个 ts包和最后⼀个 ts 包⾥加adaptation field
        #音频的每帧的时间刻度
        #显示时间: PTS = DTS + CompositionTime(offset)
        b_time = 126000
        f_timescale = self.vscale
        f_deltas = self.vdeltas
        off_n = offset / f_deltas
        video_frame_rate = f_timescale / f_deltas
        f_dts = int(b_time + iframe*(90000 / video_frame_rate))
        f_pts = int(b_time + (iframe+off_n)*(90000 / video_frame_rate))
        return self.dts_fmt(f_dts), self.pts_fmt(f_pts)

    #获取当前帧的DTS用于设置PCR
    def getDTS(self, iframe):
        #PCR是节目时钟参考，也是一种音视频同步的时钟，pcr、dts、pts 都是对同⼀个系统时钟的采样值，pcr 是递增的，因此可以将其设置为 dts 值,
        # ⾳频数据不需要 pcr(PCR的pid，一般与视频的pid是同一个值)。打包 ts 流时 PAT 和 PMT 表(属于文本数据)是没有 adaptation field，
        # 视频流和⾳频流都需要加 adaptation field
        # 音视频数据需要adaptation field。一般在⼀个帧的第⼀个 ts包和最后⼀个 ts 包⾥加adaptation field
        #音频的每帧的时间刻度
        b_time = 133500
        f_timescale = self.vscale
        f_deltas = self.vdeltas
        video_frame_rate = f_timescale / f_deltas
        f_dts = int(b_time + iframe*(90000 / video_frame_rate))
        return f_dts

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

    pes = PesPack(1,1,1,1)
    start = datetime.datetime.now()
    # ts.getPAT()
    # ts.getPMT()
    pes.pts_fmt(18163500)
    # pes.vpack(123)    
    # metad.mkM3u8()         
    end = datetime.datetime.now()     
    print(str(end-start)+" 秒")
