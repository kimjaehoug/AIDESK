// Regression checks in an isolated DOM: no SSH commands or AI messages are sent.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element{
 constructor(tag='div'){this.tagName=tag;this.children=[];this.parentElement=null;this.className='';this.style={setProperty(){}};this._html='';this.textContent='';this.scrollTop=0;this.scrollHeight=1000;this.clientHeight=100;this.classList={add:(...v)=>this.changeClass(v,true),remove:(...v)=>this.changeClass(v,false),contains:v=>this.className.split(' ').includes(v),toggle:(v,on)=>this.changeClass([v],on??!this.className.split(' ').includes(v))}}
 changeClass(values,on){const set=new Set(this.className.split(' ').filter(Boolean));for(const v of values)on?set.add(v):set.delete(v);this.className=[...set].join(' ')}
 get isConnected(){return Boolean(this.parentElement)||this.root===true}get firstChild(){return this.children[0]||null}get lastChild(){return this.children.at(-1)||null}get nextSibling(){return this.parentElement?.children[this.parentElement.children.indexOf(this)+1]||null}
 append(...nodes){for(const n of nodes){n.remove();n.parentElement=this;this.children.push(n)}}insertBefore(n,before){n.remove();n.parentElement=this;const index=this.children.indexOf(before);if(index<0)this.children.push(n);else this.children.splice(index,0,n)}remove(){if(this.parentElement){this.parentElement.children.splice(this.parentElement.children.indexOf(this),1);this.parentElement=null}}replaceChildren(...nodes){for(const n of [...this.children])n.remove();this.append(...nodes)}
 set innerHTML(value){this._html=value;this.replaceChildren();if(value.includes('stream-dots'))this.append(new Element('span'),new Element('span'))}get innerHTML(){return this._html}
 insertAdjacentHTML(position,html){const n=new Element('span');n.innerHTML=html;this.append(n)}
 find(id){if(this.id===id)return this;for(const n of this.children){const found=n.find(id);if(found)return found}return null}
}
const root=new Element();root.root=true;for(const id of ['historyContent','motionEnabled','streamEnabled','streamSpeed','motionPreview','historyAutoStatus']){const node=new Element();node.id=id;root.append(node)}
const document={createElement:tag=>new Element(tag),getElementById:id=>root.find(id),documentElement:new Element()};
const html=fs.readFileSync(new URL('../index.html','file://'+__filename),'utf8');
const code=html.slice(html.indexOf('// Conversation nodes survive'),html.indexOf('function maybeRefreshHistory()'));
const context=vm.createContext({document,window:{matchMedia:()=>({matches:false,addEventListener(){}})},performance:{now:()=>0},requestAnimationFrame:()=>1,cancelAnimationFrame(){},setTimeout,clearTimeout,console});
vm.runInContext(`const $=id=>document.getElementById(id);let state={settings:{ui_motion:true,ui_stream:true,stream_speed:180}};let deskSession={provider:'Claude',host:'local',id:'test'};let terminal=null;function sessionKey(s){return JSON.stringify([s.provider,s.host,s.id])}function renderMarkdown(t){return 'MD:'+t}function esc(t){return t}function displayMessageText(t){return t.trim()}function renderSessionModel(){};`+code,context);
const run=source=>vm.runInContext(source,context);
run(`resetHistoryView(sessionKey(deskSession));renderHistoryMessages({messages:[{id:'1',role:'user',text:'질문'},{id:'2',role:'assistant',text:'기존 답변'}]},true)`);
const previous=root.find('historyList').children[1];assert.equal(previous._shown,'기존 답변');
root.find('historyContent').scrollTop=100;
run(`renderHistoryMessages({messages:[{id:'1',role:'user',text:'질문'},{id:'2',role:'assistant',text:'기존 답변'},{id:'3',role:'assistant',text:'한국어 스트리밍 답변 🙂 문장이 이어집니다. '.repeat(20)}]},false);tickMessages(100)`);
assert.equal(root.find('historyList').children[1],previous,'refresh must preserve existing message nodes');
assert.equal(root.find('historyContent').scrollTop,100,'reading older messages must not jump to the bottom');
const reply=root.find('historyList').lastChild;assert(reply._shown.length>0&&reply._shown.length<600,'a new reply must appear progressively');assert(reply.classList.contains('message-writing'));
run('finishMessageAnimations()');assert(reply._shown.endsWith('이어집니다. '));assert(!reply.classList.contains('message-writing'));
run(`beginStreamTurn('새 질문');currentStreamTurn().sending=false;currentStreamTurn().parts=[{text:'아주 긴 한국어 답변입니다',node:null,savedKey:null}];renderStreamTurn();tickMessages(100)`);
assert(root.find('pendingUser'));assert(root.find('liveReply'));
const livePart=root.find('liveReply').firstChild;
const streamedPrefix=livePart._shown;
assert(streamedPrefix.length>0);
run(`renderHistoryMessages({messages:[...historyMessages,{id:'4',role:'user',text:'새 질문'},{id:'5',role:'assistant',text:'아주 긴 **한국어 답변**입니다'}]},false)`);
assert.equal(root.find('pendingUser'),null,'optimistic user message must disappear after the log confirms it');
assert.equal(root.find('liveReply').children.length,1,'saved partial reply must replace the live bubble, not duplicate it');
const saved=root.find('historyList').lastChild;
assert(saved._shown.length>=streamedPrefix.length,'saved Markdown must inherit the visible reveal cursor');
run('tickMessages(200)');const beforeFinish=saved._shown;
run('currentStreamTurn().idle=true;reconcileStreamTurn()');assert.equal(root.find('liveReply'),null);
assert.equal(saved._shown,beforeFinish,'completion must not reset the reveal cursor');
run('finishMessageAnimations()');
// A tool boundary creates a second stable message rather than rewriting the first.
run(`beginStreamTurn('여러 단계');currentStreamTurn().sending=false;currentStreamTurn().parts=[{text:'먼저 확인한 결과입니다.',node:null,savedKey:null},{text:'도구 실행 후의 다음 답변입니다.',node:null,savedKey:null}];renderStreamTurn();tickMessages(100)`);
const wrapper=root.find('liveReply');const firstPart=wrapper.children[0],secondPart=wrapper.children[1];
assert.equal(wrapper.children.length,3,'both answer blocks and one status must be visible');
run(`renderHistoryMessages({messages:[...historyMessages,{id:'6',role:'user',text:'여러 단계'},{id:'7',role:'assistant',text:'먼저 확인한 결과입니다.'}]},false)`);
assert.equal(wrapper.children.length,2,'only the saved block must leave the live preview');
assert.equal(wrapper.firstChild,secondPart,'the next answer must keep the same node and reveal cursor');
run(`currentStreamTurn().parts[1].text+=' 추가 내용.';renderStreamTurn()`);
assert.equal(wrapper.firstChild,secondPart,'growing answer must not be recreated');
run(`renderHistoryMessages({messages:[...historyMessages,{id:'8',role:'assistant',text:'도구 실행 후의 다음 답변입니다. 추가 내용.'}]},false);currentStreamTurn().idle=true;reconcileStreamTurn()`);
assert.equal(root.find('liveReply'),null);
// An empty input prompt is visible before the first token and is not a completed answer.
run(`beginStreamTurn('첫 토큰 대기');currentStreamTurn().sending=false;currentStreamTurn().idle=true;renderHistoryMessages({messages:[...historyMessages,{id:'waiting',role:'user',text:'첫 토큰 대기'}]},false)`);
assert(run('Boolean(currentStreamTurn())'),'empty input before the first token must not end the turn');
run('removeLiveReply();streamTurns.clear()');
// Log polling can win the race; it must not terminate a Claude turn before PTY data arrives.
run(`beginStreamTurn('레이스 확인');currentStreamTurn().sending=false;renderHistoryMessages({messages:[...historyMessages,{id:'9',role:'user',text:'레이스 확인'},{id:'10',role:'assistant',text:'먼저 저장된 답변입니다.'}]},false)`);
assert(run('Boolean(currentStreamTurn())'),'a saved reply before terminal polling must not terminate streaming');
run(`currentStreamTurn().parts=[{text:'먼저 저장된 답변입니다.',node:null,savedKey:null}];reconcileStreamTurn()`);
assert.equal(root.find('liveReply').children.length,1,'later terminal data must not replay an already visible saved reply');
run('removeLiveReply();streamTurns.clear();finishMessageAnimations()');
// Terminal wrapping and Markdown decoration changes must not restart a visible reply.
run(`updateMessageNode(historyNodes.get('assistant:5'),'아주 긴 한국어\\n답변입니다',false);updateMessageNode(historyNodes.get('assistant:5'),'아주 긴 **한국어 답변**입니다. 더 이어짐',true)`);
assert(run(`historyNodes.get('assistant:5')._shown.length>0`),'wrapped text must retain its reveal cursor');
run(`beginStreamTurn('전송 실패');currentStreamTurn().failed=true;reconcileStreamTurn()`);assert.equal(root.find('pendingUser'),null);assert.equal(root.find('liveReply'),null);
run(`state.settings.ui_motion=false;updateMessageNode(historyNodes.get('assistant:5'),'즉시 표시',true)`);assert.equal(run("historyNodes.get('assistant:5')._shown"),'즉시 표시');
run(`terminal={buffer:{active:{length:3,getLine:i=>[{isWrapped:false,translateToString:trim=>trim?'hello':'hello '},{isWrapped:true,translateToString:()=> 'world'},{isWrapped:false,translateToString:()=>''}][i]}}}`);
assert.equal(run('terminalLogicalRows()[0]'),'hello world','terminal wraps must retain the boundary space');
assert.equal(run(`markdownRevealPrefix('한국어 🙂 **답변**입니다','한국어 🙂 답변')`),'한국어 🙂 **답변','Markdown cursor translation must preserve emoji and revealed text');
// Exercise actual PTY snapshot -> live DOM -> log handoff -> next block -> completion.
run(`streamTurns.clear();resetHistoryView(sessionKey(deskSession));renderHistoryMessages({messages:[]},true);terminal=null;beginStreamTurn('실제 순서');currentStreamTurn().sending=false;historyBusy=true;function terminalRows(rows){terminal={buffer:{active:{length:rows.length,getLine:i=>({isWrapped:false,translateToString:()=>rows[i]})}}}}terminalRows(['❯ 실제 순서','● 첫 번째 답변이 점점 이어집니다.','✻ Working…','❯']);scanConversationStream();tickMessages(100)`);
const actualLive=root.find('liveReply').firstChild, actualShown=actualLive._shown;
assert(actualShown.length>0);
run(`renderHistoryMessages({messages:[{id:'s1',role:'user',text:'실제 순서'},{id:'s2',role:'assistant',text:'첫 번째 **답변이 점점** 이어집니다.'}]},false)`);
assert.equal(root.find('liveReply').children.length,1,'PTY and log polling must render one copy');
assert(root.find('historyList').lastChild._shown.length>=actualShown.length);
run(`terminalRows(['❯ 실제 순서','● 첫 번째 답변이 점점 이어집니다.','● Bash(pwd)','  ⎿ 결과','● 두 번째 답변입니다.','✻ Working…','❯']);scanConversationStream();tickMessages(200)`);
assert.equal(root.find('liveReply').children.length,2,'only the unsaved second answer and status must appear');
const actualSecond=root.find('liveReply').firstChild;
run(`scanConversationStream()`);assert.equal(root.find('liveReply').firstChild,actualSecond,'repeated PTY snapshots must not recreate the message');
run(`renderHistoryMessages({messages:[...historyMessages,{id:'s3',role:'assistant',text:'두 번째 답변입니다.'}]},false);terminalRows(['❯ 실제 순서','● 첫 번째 답변이 점점 이어집니다.','● Bash(pwd)','  ⎿ 결과','● 두 번째 답변입니다.','✻ Brewed for 3s · done','❯']);scanConversationStream()`);
assert.equal(root.find('liveReply'),null,'final PTY snapshot must remove the preview without replaying saved replies');
assert.equal(root.find('historyList').children.length,3);
run(`const cursorNode=createMessageNode({role:'assistant',text:''});$('historyList').append(cursorNode);cursorNode.classList.add('message-writing');const cursorPart={node:createMessageNode({role:'assistant',text:''})};cursorPart.node._shown='완료된 문장';handoffStreamPart(cursorPart,cursorNode,'완료된 문장');globalThis.cursorNode=cursorNode`);
assert(!run(`cursorNode.classList.contains('message-writing')`),'a fully revealed handoff must remove the typing cursor');
run(`beginStreamTurn('즉시 중단');interruptStreamTurn()`);assert.equal(root.find('liveReply'),null,'interrupt before the first token must clear the waiting preview');
console.log('Conversation motion: node reuse, progressive Korean text, scroll preservation, deduplication, failure cleanup and motion toggle passed.');
