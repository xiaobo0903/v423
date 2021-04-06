#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2021-present, sun-shine cloud, Inc.
# All rights reserved.
# 读取配置项的内容记录；

import os
import configparser

class cfgClass():

    def __init__(self):
        ilevel ={"CRITICAL":50, "ERROR":40, "WARNING":30, "INFO":20, "DEBUG":10, "NOTSET":0}
        path_file = "config.ini"
        curpath = os.path.dirname(os.path.realpath(__file__))
        cfgpath = os.path.join(curpath, path_file)
        config = configparser.ConfigParser()
        config.read(cfgpath)
        level = config['log']['level'].upper()
        self.level = ilevel[level]
        self.file = config['log']['file']
        self.host = config['redis']['host']
        self.port = config['redis']['port']
        self.db = config['redis']['db']
        self.BASE_URL = config['ts']['BASE_URL']
        self.TMP_PATH = config['ts']['TMP_PATH']

