// 用构造的 initialData 做解析器单测（不联网）
import { parseQuestion, stripHtml } from './zhihu.mjs';

const html = `<!DOCTYPE html><html><head><title>x</title></head><body>
<script id="js-initialData" type="text/json">${JSON.stringify({
  initialState: {
    entities: {
      questions: {
        123: { id: 123, title: '测试问题标题？', answerCount: 42, followerCount: 7, visitCount: 999, detail: '<p>问题描述<b>加粗</b></p>' }
      },
      answers: {
        9001: { id: 9001, voteupCount: 10, commentCount: 2, createdTime: 1700000000, author: { name: '低赞答主' }, content: '<p>内容A &amp; B</p>' },
        9002: { id: 9002, voteupCount: 300, commentCount: 5, createdTime: 1700000001, author: { name: '高赞答主' }, content: '<p>内容C</p><figure>图</figure>' }
      }
    }
  }
})}</script></body></html>`;

const q = parseQuestion(html);
const checks = [
  ['问题ID', q.问题ID === 123],
  ['标题', q.标题 === '测试问题标题？'],
  ['回答数', q.回答数 === 42],
  ['关注数', q.关注数 === 7],
  ['浏览数', q.浏览数 === 999],
  ['首屏答案数=2', q.首屏答案数 === 2],
  ['按赞数降序', q.答案[0].答主 === '高赞答主'],
  ['作者名', q.答案[1].答主 === '低赞答主'],
  ['实体解码', q.答案[1].内容 === '内容A & B'],
  ['图片占位', q.答案[0].内容.includes('[图片]')],
  ['详情去标签', q.详情 === '问题描述加粗'],
  ['stripHtml 去标签', stripHtml('<b>x</b>y') === 'xy']
];

let ok = 0;
for (const [name, pass] of checks) {
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${name}`);
  if (pass) ok++;
}
console.log(`\n${ok}/${checks.length} 通过`);
process.exit(ok === checks.length ? 0 : 1);
