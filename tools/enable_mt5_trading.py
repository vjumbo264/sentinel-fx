#!/usr/bin/env python3
"""Configure actual terminal data paths before restart; require demo and AutoTrading.
Credentials come from environment, never from interpolated shell/Python text.
"""
import os,time,json,subprocess
import rpyc
port=int(os.environ.get('MT5_PORT','18812'))
login=int(os.environ.get('MT5_DEMO_LOGIN') or os.environ['MT5_LOGIN'])
password=os.environ['MT5_PASSWORD'];server=os.environ.get('MT5_DEMO_SERVER') or os.environ['MT5_SERVER']
c=rpyc.classic.connect('localhost',port);c._config['sync_request_timeout']=60
mt5=c.modules.MetaTrader5
assert mt5.initialize(timeout=20000), 'Terminal initialize failed'
assert mt5.login(login=login,password=password,server=server), 'Demo login failed'
a=mt5.account_info();assert a and int(a.trade_mode)==0 and int(a.login)==login, 'Refusing non-demo account'
ti=mt5.terminal_info();print('Terminal state:',json.dumps({'path':str(ti.path),'data_path':str(ti.data_path),'trade_allowed':bool(ti.trade_allowed)}))
# Gracefully stop the terminal before writing files: terminal otherwise overwrites them.
c.execute('import MetaTrader5, os, subprocess, configparser, time')
c.namespace['sfx_path']=str(ti.path);c.namespace['sfx_data']=str(ti.data_path)
c.namespace['sfx_login']=login;c.namespace['sfx_password']=password;c.namespace['sfx_server']=server
c.execute('''
MetaTrader5.shutdown()
subprocess.run(['taskkill','/IM','terminal64.exe','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
time.sleep(2)
for filename in [os.path.join(sfx_data,'config','common.ini'),os.path.join(sfx_path,'config','common.ini')]:
    os.makedirs(os.path.dirname(filename),exist_ok=True)
    cfg=configparser.ConfigParser(strict=False);cfg.optionxform=str
    if os.path.exists(filename):
        raw=open(filename,'rb').read()
        for enc in ('utf-16','utf-16le','utf-8-sig'):
            try:
                cfg.read_string(raw.decode(enc));break
            except (UnicodeError,configparser.Error):pass
    if not cfg.has_section('Experts'):cfg.add_section('Experts')
    for key in ('AllowLiveTrading','Enabled','AllowDllImport'):cfg.set('Experts',key,'1')
    for key in ('Account','Profile'):cfg.set('Experts',key,'0')
    with open(filename,'w',encoding='utf-16') as f:cfg.write(f,space_around_delimiters=False)
startup=os.path.join(sfx_path,'sfx-startup.ini')
with open(startup,'w',encoding='utf-16') as f:
    f.write('[Common]\\nLogin='+str(sfx_login)+'\\nPassword='+sfx_password+'\\nServer='+sfx_server+'\\n[Experts]\\nAllowLiveTrading=1\\nEnabled=1\\nAllowDllImport=1\\nAccount=0\\nProfile=0\\n')
subprocess.Popen([os.path.join(sfx_path,'terminal64.exe'),'/config:'+startup],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
''')
for attempt in range(30):
 time.sleep(2)
 if mt5.initialize(timeout=10000) and mt5.login(login=login,password=password,server=server):
  ti=mt5.terminal_info()
  if ti and ti.trade_allowed:break
else:
 # Independent method: toggle the AlgoTrading toolbar using the live Wine display.
 name=os.environ.get('MT5_CONTAINER_NAME','mt5-stack')
 subprocess.run(['docker','exec','-u','root',name,'bash','-lc','apt-get update -qq && apt-get install -qq -y xdotool'],check=True,timeout=180)
 subprocess.run(['docker','exec',name,'bash','-lc',"export DISPLAY=${DISPLAY:-:0}; W=$(xdotool search --name 'MetaTrader|Deriv' | head -1); test -n \"$W\"; xdotool windowactivate --sync \"$W\"; xdotool key --clearmodifiers ctrl+e"],check=True,timeout=30)
 time.sleep(3)
a=mt5.account_info();ti=mt5.terminal_info()
assert a and int(a.trade_mode)==0 and int(a.login)==login,'Refusing non-demo account after restart'
assert ti and ti.trade_allowed,'Terminal AlgoTrading remains disabled after configuration/restart and UI toggle'
print('VERIFIED terminal_info.trade_allowed=True; account trade_mode=DEMO')
c.execute("os.remove(startup) if os.path.exists(startup) else None; sfx_password=None")
c.close()
