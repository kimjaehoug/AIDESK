"""Create a controlling terminal in a fresh child, then launch the selected CLI."""
import fcntl,os,sys,termios
try:fcntl.ioctl(0,termios.TIOCSCTTY,0)
except OSError:pass
try:os.execvpe(sys.argv[1],sys.argv[1:],os.environ)
except OSError as error:
 print('AI Desk: '+str(error),file=sys.stderr);raise SystemExit(127)
