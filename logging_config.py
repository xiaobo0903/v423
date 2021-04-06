import logging
import cfg

class Config():
    
    def __init__(self):

        scfg = cfg.cfgClass()
        # creating a logger对象
        self.logger = logging.getLogger()    

        # define the default level of the logger
        self.logger.setLevel(scfg.level)  
        
        # creating a formatter
        formatter = logging.Formatter( '%(asctime)s | %(levelname)s -> %(message)s' )  
        
        # creating a handler to log on the filesystem  
        file_handler=logging.FileHandler(scfg.file)
        file_handler.setFormatter(formatter)  
        file_handler.setLevel(scfg.level)  
        
        console = logging.StreamHandler()
        console.setLevel(scfg.level)
        console.setFormatter(formatter)  

        # adding handlers to our logger  
        self.logger.addHandler(console)   
        self.logger.addHandler(file_handler) 
        
        #logger.info('this is a log message...')  
    
    def get_config(self):    
        return self.logger