"""App-owned macOS window placement; no accessibility/UI automation."""
import ctypes as C
import sys

class DesktopLayer:
    def __init__(self):
        self.available=sys.platform=='darwin'
        if not self.available: return
        C.CDLL('/System/Library/Frameworks/AppKit.framework/AppKit')
        self.objc=C.CDLL('/usr/lib/libobjc.A.dylib')
        self.objc.objc_getClass.argtypes=[C.c_char_p]; self.objc.objc_getClass.restype=C.c_void_p
        self.objc.sel_registerName.argtypes=[C.c_char_p]; self.objc.sel_registerName.restype=C.c_void_p
        self.address=C.cast(self.objc.objc_msgSend,C.c_void_p).value
        self.cg=C.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
        self.cg.CGWindowLevelForKey.argtypes=[C.c_int]; self.cg.CGWindowLevelForKey.restype=C.c_int32
    def send(self,obj,selector,restype=C.c_void_p,argtypes=(),args=()):
        fn=C.CFUNCTYPE(restype,C.c_void_p,C.c_void_p,*argtypes)(self.address)
        return fn(obj,self.objc.sel_registerName(selector.encode()),*args)
    def window(self,title):
        app=self.send(self.objc.objc_getClass(b'NSApplication'),'sharedApplication')
        windows=self.send(app,'windows'); count=self.send(windows,'count',C.c_ulong)
        for i in range(count):
            window=self.send(windows,'objectAtIndex:',argtypes=(C.c_ulong,),args=(i,))
            string=self.send(window,'title'); text=self.send(string,'UTF8String',C.c_char_p)
            if text and text.decode()==title: return window
        return None
    def apply(self,title,embedded=True):
        if not self.available: return False
        window=self.window(title)
        if not window: return False
        # Desktop-icon level + 1 stays on the desktop, below ordinary apps, and receives clicks.
        level=self.cg.CGWindowLevelForKey(18)+1 if embedded else 0
        self.send(window,'setLevel:',None,(C.c_long,),(level,))
        self.send(window,'setCollectionBehavior:',None,(C.c_ulong,),(1|16|64 if embedded else 0,))
        self.send(window,'setHasShadow:',None,(C.c_bool,),(False if embedded else True,))
        self.send(window,'setHidesOnDeactivate:',None,(C.c_bool,),(False,))
        self.send(window,'setIgnoresMouseEvents:',None,(C.c_bool,),(False,))
        self.send(window,'setAcceptsMouseMovedEvents:',None,(C.c_bool,),(True,))
        self.send(window,'orderFrontRegardless',None)
        return self.send(window,'level',C.c_long)==level
