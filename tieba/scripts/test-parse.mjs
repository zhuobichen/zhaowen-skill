// 用真实抓到的移动版片段做解析器单测（不联网）
import { parseThreadList, normalizeCookie } from './tieba.mjs';

const fixture = `<ul class="threads_list" id="frslistcontent"><li class="tl_top scale-1px-bottom" data-tid="11085093277" data-floor="0" data-thread-type="0"><a href="/p/11085093277?lp=5028&amp;mo_device=1&amp;is_jingpost=0" data-thread-type="0" class="j_common ti_item no_border top" data-floor="0" tid="11085093277" data-tid="11085093277" tasktype=""><div class="ti_title">            <span class="ti_title_icon ti_icon_zhiding">置顶</span>            <span>【2026年10月】10月装机走向与推荐（总第125期）</span></div></a></li><li class="tl_top scale-1px-bottom" data-tid="10183774294" data-floor="0" data-thread-type="0"><a href="/p/10183774294?lp=5028&amp;mo_device=1" class="j_common ti_item" data-tid="10183774294"><div class="ti_title"><span>河野华这么可爱，你们怎么忍心黑她？</span></div></a></li><li class="tl_top scale-1px-bottom" data-tid="99887766" data-floor="0"><a href="/p/99887766" class="j_common ti_item"><div class="ti_title"><span class="ti_title_icon ti_icon_jinghua">精品</span><span>典中典之未成年 令人忍俊不禁 长图</span></div></a></li></ul>`;

const list = parseThreadList(fixture);
console.log(`解析到 ${list.length} 条`);
for (const t of list) console.log(`  tid=${t.tid} 置顶=${t.置顶} 精品=${t.精品} 标题=${t.title}`);

const checks = [
  ['条数=3', list.length === 3],
  ['第1条 tid', list[0]?.tid === '11085093277'],
  ['第1条置顶', list[0]?.置顶 === true],
  ['第1条标题去掉徽标', list[0]?.title === '【2026年10月】10月装机走向与推荐（总第125期）'],
  ['第2条标题', list[1]?.title === '河野华这么可爱，你们怎么忍心黑她？'],
  ['第3条精品', list[2]?.精品 === true],
  ['cookie 只给值', normalizeCookie('abc123') === 'BDUSS=abc123'],
  ['cookie 整串', normalizeCookie('BDUSS=x; STOKEN=y') === 'BDUSS=x; STOKEN=y']
];

let ok = 0;
for (const [name, pass] of checks) {
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${name}`);
  if (pass) ok++;
}
console.log(`\n${ok}/${checks.length} 通过`);
process.exit(ok === checks.length ? 0 : 1);
