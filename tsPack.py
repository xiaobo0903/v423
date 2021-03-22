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

class tsPack():

    #获取的mp4片段的数据内容
    mp4data = None
    #对于文件的绝对偏移量；abs_soff 起始偏移量 abs_eoff终止偏移量；
    abs_soff = 0
    abs_eoff = 0

    def __init__(self, mp4_md5, start, end):

        #根据mp4_md5获取redis中的数据,因为数组中保存的序号是从0开始的，所以起始与终止的数都减1，以与实际数组的内容对应；
        self.start = start - 1
        self.end = end - 1
        self.mp4_md5 = mp4_md5
        trakdata = trakData()
        #通过mp5获取原始mp4文件的url访问地址（redis)；
        self.url = trakdata.getMp4Url(mp4_md5)
        self._vtrak = None
        self._atrak = None
        #通过md5获取保存在redis中的mp4相关头数据信息
        self._vtrak, self._atrak = trakdata.getTrakData(mp4_md5)
        #初始化设置pes打包实例
        self.pes_pack = PesPack(self._vtrak.timescale, self._vtrak.sample_deltas, self._atrak.timescale, self._atrak.sample_deltas)
        return
        
    #根据video请求来的内容来生成TS的文件
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
        start_aoff = self._atrak.sample_offset[a_start]
        end_aoff = self._atrak.sample_offset[a_end]
        #######################################################################
        # start_off = start_voff if start_aoff > start_voff else start_aoff 
        # end_off = end_voff if end_voff > end_aoff else end_aoff 
        start_off = start_voff
        end_off = end_voff
        self.abs_offset = start_off
        return start_off, end_off

    #获取mp4片段的数据内容
    def getMp4Data(self):

        s_off, e_off = self.getFileOffset()
        tools = mp4Tools()

        self.mp4data = tools.down_Mp4Slice(self.url, self.mp4_md5, s_off, e_off)
        self.abs_soff = s_off
        self.abs_eoff = e_off

    #生成TS
    def getTS(self):
        #从远程服务器上下载相应的片段内容；
        self.getMp4Data()
        #获取到了原始文件中的相应数据内容；全部帧数据封装后的数组内容
        data_a = self.mk_TSPackages()
        with open("mmmm.ts", "wb") as f:        
            for d in data_a:
                f.write(d)
        return

    #获取SPS的NALU数据
    def getSPSNalu(self):
        #每个nalu的头部都加 0x00 0x00 0x00 0x01四个字节的头； 
        start_code = [0x00, 0x00, 0x00, 0x01, 0x27]
        sps_data = start_code + self._vtrak.sps
        return sps_data

    #获取PPS的NALU数据
    def getPPSNalu(self):
        #每个nalu的头部都加 0x00 0x00 0x00 0x01四个字节的头；         
        start_code = [0x00, 0x00, 0x00, 0x01, 0x28]
        pps_data = start_code + self._vtrak.pps
        return pps_data

    # #获取每一帧的NALU数据, iframe是帧号
    # def getFrameNalu(self, ifream):
    #     #每个nalu的头部都加 0x00 0x00 0x00 0x01四个字节的头； 
    #     start_code = [0x00, 0x00, 0x01]
    #     f_data = self.getFrameData(ifream)
    #     f_data1 = start_code + f_data
    #     return f_data1  
    
    #获取帧数据,在取帧数据时，会不会有帧数据会分chunk的情况（看网上说的一帧只能在一个chunk内，但是不是这样目前还不确定，如果有的话，会有风险!!!）
    def getFrameData(self, ifream):
        f_soff = self._vtrak.sample_offset[ifream]
        f_size = self._vtrak.sample_size[ifream]
        f_eoff = f_soff + f_size
        f_data = self.mp4data[f_soff-self.abs_soff:f_eoff-self.abs_soff]
        #因为提取的h264内容，前四个字节是代表长度，需要把长度的四个字节替换成0x00 0x00 0x00 0x01,这样就完成了NALU的封装的工作；
        a_fdat = f_data

        olen = len(a_fdat)
        o_len = a_fdat[:4]
        h_int = int.from_bytes(o_len, byteorder='big', signed=False)
        if o_len == h_int + 4:
            a_fdat = a_fdat[4:]
            return a_fdat

        #在此只去掉SEI的内容，只保留帧的内容即可；
        while True:
            v_type = a_fdat[4] 
            v_len = a_fdat[:4]
            h_int1 = int.from_bytes(v_len, byteorder='big', signed=False)

            v_type1 = v_type&0x1F
            if h_int1 > len(a_fdat):
                a_fdat = f_data
                break
            if v_type1 in (0x01, 0x02, 0x03, 0x04, 0x05):
                a_fdat = a_fdat[4:]
                break
            a_fdat = a_fdat[h_int1+4:]

        return a_fdat

    # #根据起始的帧和终止帧提取数据中的NALU的内容；
    def mk_TSPackages(self):
        #根据帧数来生成TS的数据
        self.counter = 0
        ts_all = []
        #在进行nalu封装的时候，需要设定帧开始的标志 0x0000000109f0
        nau = [0x00, 0x00, 0x00, 0x01, 0x09, 0xf0]
        nalu = [0x00, 0x00, 0x00, 0x01]        
        # nalu_k = [0x00, 0x00, 0x00, 0x01, 0x65]
        # nalu_nk = [0x00, 0x00, 0x00, 0x01, 0x61]
        for i in range(self.start, self.end):
            #返回帧的原始数据
            f_data = self.getFrameData(i)
            # self.printHex(f_data, 1024*1024)
            #把帧的原始数据进行ES打包
            # f_data1 = self.pes_pack.mkEsData(f_data)

            f_data1 = bytes(nalu) + f_data
            #如果是第一帧还需要加入SPS和PPS的信息, 另外第一帧为关键帧所以需要加入valu的标志65
            if i == self.start:
                f_data1 = bytes(nalu)+ self._vtrak.sps + bytes(nalu)+ self._vtrak.pps + bytes(nalu) + f_data
            #nalu = 帧数据+sps+pps, 如果打成PES包，还需要加上包头 pes = pes包头+nalu
            offset = self._vtrak.sample_decode_off[i]
            f_data1 = bytes(nau) + f_data1
            pes_data = self.pes_pack.mk_pesData(i, offset, f_data1)
            #每个帧的头一个包中应含有PCR的内容
            pcr = self.pes_pack.getDTS(i)
            ts_f_data = self.ts_vpack(pes_data, pcr)
            ts_all = ts_all + ts_f_data
        pat = self.getPAT()
        pmt = self.getPMT()
        ts_all1 = []
        ts_all1.append(bytes(pat))
        ts_all1.append(bytes(pmt))        
        ts_all1 = ts_all1 + ts_all
        return ts_all1
    
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
        pcr1 = (0x000000000000|pcr)<<15
        # pcr_a = struct.pack("6b", pcr1)
        pcr_a = pcr1.to_bytes(6, byteorder='big')
        #做为填充字段，则需要设置一个PCR的标志位，长度后面+PCR的标志，所以一共有两个占位字节，如果有PCR则需要设置为0x10，如果没有则设置为0x00:
        #PCR的内容一共占6个字节（48位），加上一个字节表示PCR的标志位(pcr_flag=0x10),所以PCR的内容一共占7位；
        #因为默认都加了自填充字段，所以前面还需要有一位的自适应的长度字段（默认:0x07),所以最小的长度应该是pesdata的长度加上8位；
        #如果只缺一个字符即可完成自适应的可以在pesdate前加一个0x00字节，做为调节字节；
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
        pat_d = [0x47, 0x40, 0x00, 0x10, 0x00, 0x00, 0xB0, 0x0D, 0x00, 0x01, 0xC1, 0x00, 0x00, 
        #表示这是一个PAT
        0x00, 0x01,
        #表示这个PID= 1 0000 0000 0000 
        0xF0, 0x00, 
        0x2A, 0xB1, 0x04, 0xB2]
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
        pmt_d = [0x47, 0x50, 0x00, 0x10, 0x00, 
                0x02, 
                0xB0, 0x1D, 
                0x00, 0x01, 
                0xC1, 0x00,
                #指定视频的pid（package - id)
                0x00, 0xE1, 
                0x00, 0xF0, 0x00, 
                0x1B, 0xE1, 
                0x00, 0xF0, 
                0x00, 0x0F, 
                0xE1, 0x01, 0xF0, 0x06, 0x0A, 
                0x04, 0x7A, 0x68, 0x6F, 0x00, 
                0x11, 0x65, 0x79, 0x85]
                
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

    # #根据起始的帧和终止帧提取数据中的NALU的内容；
    # def getVideoNALUData(self, sframe, eframe, vdata):
    
    #     self.vframelist = []
    #     s = eframe - sframe
    #     s_offset = self.abs_offset
    #     f = open("lldq_"+str(sframe)+"_"+str(eframe)+".h264", "wb+")
    #     i_head = struct.pack('3x1b',1)
    #     f.write(i_head)
    #     f.write(self._vtrak.sps)
    #     f.write(i_head)        
    #     f.write(self._vtrak.pps)        
    #     for k in range(0, s):
    #         vdata1 = None
    #         s_pos =  self._vtrak.sample_offset[sframe+k-1]
    #         p_size =  self._vtrak.sample_size[sframe+k-1]            
    #         c_offset = s_pos - s_offset
    #         #获取前端的4个字节，变换成长度，一个nalu中可能存在多个帧的情况，该种情况，可以通过检查sample_size与s_len的长度来进行判读，
    #         #如果s_len的长度小于sample_size说明后面还有数据面要处理；
    #         s_alen = 0
    #         while True:
    #             s_len = vdata[c_offset+s_alen:c_offset+4+s_alen]
    #             h_int = int.from_bytes(s_len, byteorder='big', signed=False)
    #             vdata1 = vdata[c_offset+s_alen+4:c_offset+4+s_alen+h_int]
    #             self.vframelist.append(vdata1)
    #             f.write(i_head)                
    #             f.write(vdata1)
    #             # with open("lldq_"+str(10000+k)+".h264", "wb+") as f1:           
    #             #     f1.write(i_head)
    #             #     f1.write(vdata1)                  
    #             s_alen = s_alen + 4 + h_int
    #             if s_alen >= p_size:
    #                 break