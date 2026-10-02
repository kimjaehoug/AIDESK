const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('ai_dashboard/index.html','utf8');
const code=html.slice(html.indexOf('async function pollTerminal('),html.indexOf('async function stopChat('));
let scheduled,reconnects=0,calls=0;
const status={};const context={terminalGeneration:1,terminalId:'existing-connection',terminalCursor:7,deskSession:{},terminalReadFailures:0,chatConnectedAt:Date.now(),chatReconnectAttempt:0,sessionKey:()=> 'session',api:async()=>{if(calls++===0)throw Error('temporary network error');return {cursor:8,running:true,data:''}},$:()=>status,scheduleChatReconnect:()=>reconnects++,setTimeout:fn=>{scheduled=fn},Date,Math};
vm.createContext(context);vm.runInContext(code,context);
(async()=>{await context.pollTerminal(1);assert.equal(context.terminalId,'existing-connection');assert.equal(context.terminalCursor,7);assert.equal(reconnects,0);await scheduled();assert.equal(context.terminalCursor,8);assert.equal(context.terminalReadFailures,0);assert.equal(reconnects,0);console.log('PASS: transient output failure retains connection/cursor and recovers without new session')})().catch(e=>{console.error(e);process.exitCode=1});
