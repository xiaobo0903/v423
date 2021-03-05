#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2021-present, sun-shine cloud, Inc.
# All rights reserved.
# 获取到音频和视频资源后进行TS的封包操作；
# 需要校对时间戳信息，需要传入帧的起始编号，视帧的采样率、刻度；音频的采样率和刻度；
# 因为是生成流方式，如果出现数据缺失可能会造成音画不同步的现象；


import datetime
import os.path
import struct
import sys
import time
import requests
from trackClass import trackClass
from hashlib import md5
import urllib.request
import tsCRC32

class TSClass():
    
    # ifream是首帧的编号, 
    # vdata是视频帧的数据, vscale是视频采样率，vdetas是视频的刻度， 
    # adata是视频帧的数据, ascale是视频采样率，adetas是视频的刻度;
    def __init__(selfs):
        return    
    # def __init__(self, ifream, vdata, vscale, vdetas, adata, ascale, adetas):
        
    #     self.ifream = ifream
    #     self.vdata = vdata
    #     self.vscale = vscale
    #     self.vdetas = vdetas
    #     self.adata = adata
    #     self.ascale = ascale
    #     self.adetas = adetas

    # TS的基本知识：ts文件分为三次：ts层(Transport Stream)、pes层(Packet Elemental Stream)、es层(Elementary Stream)。
    # es层就是音视频数据，
    # pes层是在音视频数据上加了时间戳等数据帧的说明信息，
    # ts层是在pes层上加入了数据流识别和传输的必要信息。
    def getOneBoxData(self):
        seek = 0
        while seek < len(self._chunk):
            data = self._chunk[seek:seek+8]
            dlen, dtype = struct.unpack(">I4s", data)
            print(dtype)
            self._boxData[dtype] = self._chunk[seek+8:dlen]
            seek += dlen            
            if dtype == b"moov":
                break

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

    #获取流的PES数据
    def getPES(self, vdata):
        #pid = 0x814 音频， pid=0x810是视频
        pes_head = [0x47, 0x48, 0x14]
        a1 = 0x10

    def getPTS(self):
         else if (box_type_equa(uint32_to_str(bh.type, sbuffer), "ctts")) {
        uint32_t version = 0;
        read_net_bytes_to_host_uint32(&box[8], &version);
        if(version != 0) {
            LOG_E("ctts unsupport version :%d ", version)
            return;
        }

        uint32_t entry_cnt = 0;
        read_net_bytes_to_host_uint32(&box[12], &entry_cnt);
        char buf[128] = {0};
        tree_childs_insert_with_val(tree, "version", uint32_to_ascii(version, buf));
        tree_childs_insert_with_val(tree, "entry_cnt", uint32_to_ascii(entry_cnt, buf));
        
        uint32_t i = 0, j = 0, num = 0, pos = 16;
        for (i = 0; i < entry_cnt; i++) {
            uint32_t sample_cnt;
            read_net_bytes_to_host_uint32(&box[pos], &sample_cnt);
            pos += 4;
        
            uint32_t sample_offset;
            read_net_bytes_to_host_uint32(&box[pos], &sample_offset);
            pos += 4;

            for (j = 0; j < sample_cnt; j++) {
                PushBack_Array(pts_array, At_Array(dts_array, num++) + sample_offset);
                float dt, pt = 0.0;
                printf("dts : %9.3f ms | pts : %9.3f ms | \n", At_Array(dts_array, num - 1) / (mdhd_time_scale * 1.0), At_Array(pts_array, num - 1) / (mdhd_time_scale * 1.0));
            }

if __name__ == '__main__':

    ts = TSClass()
    start = datetime.datetime.now()
    ts.getPAT()
    ts.getPMT()    
    # metad.mkM3u8()         
    end = datetime.datetime.now()     
    print(str(end-start)+" 秒")
