// 分类规则：只做判断，不碰邮箱。sort.mjs / survey.mjs / preview.mjs 共用。
//
// 这套优先级是拿 2026-10 收件箱（1314 封 / 203 个发件人）逐封盘点后定的。
// 核心结论：**主题关键词（安全 > 钱 > 学术 > 招聘 > 游戏 > 垃圾）优先于发件域**，
// 只有“强身份域”（学术机构 / 游戏商店 / 自建服务 / 招聘 / 广告农场）才在关键词之前判定。
// 原因：qoder、brave、anaconda、vercel 这些域既发验证码也发营销，按域一刀切必然把验证码扫进推广。
export const CATS = [
  { key: "important", label: "00-重要邮件", desc: "真人直接找你办事的：老师让你审稿、HR 直接约面试、合作方直接联系 —— 需要你本人处理" },
  { key: "ci", label: "01-CI构建通知", desc: "GitHub Actions 流水线失败/完成通知" },
  { key: "daily", label: "02-个人日报", desc: "自己发给自己的日报与素材（Pilgrim Intel / 申论 / 每日一练 / 公众号日报）" },
  { key: "acad", label: "03-学术科研", desc: "ABaCAS、期刊投稿审稿、合作者往来、会议材料" },
  { key: "job", label: "04-求职校园", desc: "招聘投递、竞赛、学校事务" },
  { key: "game", label: "05-游戏娱乐", desc: "Steam / Humble / Rockstar / EA 等商店通知、促销、账号" },
  { key: "auth", label: "06-账号验证码", desc: "验证码、异地登录、设备验证、密码重置 —— 不管哪个平台发的" },
  { key: "promo", label: "07-订阅推广", desc: "AI 工具订阅、行业简报、营销邮件" },
  { key: "notice", label: "08-平台通知", desc: "npm 发布、GitHub 非 CI、QQ邮箱官方、平台服务/条款通知" },
  { key: "money", label: "09-财务账单", desc: "工资、发票、订单、收据、续费扣款" },
  { key: "work", label: "10-工作项目", desc: "自建 Gitea / HYCX 项目协作、GitHub Issue/PR 讨论" },
  { key: "spam", label: "11-垃圾广告", desc: "贷款/征信/申卡类诈骗广告、群发硬广" },
  { key: "other", label: "99-其他", desc: "人对人邮件，规则没盖住 —— 保留在收件箱不动" },
];

const SELF = "1473517806@qq.com";

// ---------------------------------------------------------------- 精确发件人
// 真人（老师、合作者、同事、直接联系你的 HR）—— 这些人发来的，默认归「00-重要邮件」，
// 因为都是直接找你办事的。想调整优先级就改这里。
const PEOPLE = new Set([
  "zhuyun@scut.edu.cn", // 老师：审稿邀请转发
  "long.sc@mail.scut.edu.cn", // 合作者：AQMAT/AQAG 数据
  "long.sc@qq.com",
  "huang.jiaoyan@epa.gov", // EPA 合作者
  "simon.heather@epa.gov",
  "jcy@unc.edu",
  "sarav@email.unc.edu",
  "sedryan@unc.edu",
  "cjang123@gmail.com", // 论文合作者
  "lijinying@smail.xtu.edu.cn",
  "icecoffee1024@qq.com",
  "wu163_1997943@163.com", // 项目合作（商务）
  "cdmaer@qq.com", // 数据库字段问题
  "2397330983kj@gmail.com",
  "chenkai@powerdekor.com.cn",
  "smse@tiangongxu.com",
  "sunweicheng@dalbergia.cn",
]);

// 只有主题在说“找你有事”时才把陌生人提到「重要邮件」
const RX_DIRECT = /(请你|请您|麻烦你|麻烦您|帮忙|帮我看|需要你|需要您|请你确认|请确认|请回复|回复我|审稿邀请|邀请您评审|邀请您审稿|Invitation to review|reviewer invitation|request for review|面试邀请|约面试|电话沟通|合作意向|项目合作|进度报告|需要材料|waiting for your|your input|please review|please confirm)/i;
// 群发/系统发件人不参与“重要”判定
const RX_BULK = /(noreply|no-reply|do-?not-?reply|notifications?@|mailer@|news@|marketing@|promo|mailchimp|sendgrid|amazonses|mandrill|exacttarget|edm)/i;

// 只放“域规则判不对”的：合作者私人邮箱、自建服务、招聘平台、广告农场。
const SENDERS = {
  // 学术合作者（用机构之外邮箱发来的，必须单独记）
  "long.sc@qq.com": "acad",
  "jxing3@utk.edu": "acad",
  "icecoffee1024@qq.com": "acad",
  "review@mail.paperreview.ai": "acad",
  "ncdc@lzb.ac.cn": "acad",
  "abacaswebsite@163.com": "acad",
  // 自建服务
  "hycx2019@ciestgd.com": "work",
  "gitea@hycx-gd.cn": "work",
  "logto@hycx-gd.cn": "work",
  // 平台官方
  "zhaowen@agent.qq.com": "notice",
  "postmaster@qq.com": "notice",
  "admin@qq.com": "notice",
  "10000@qq.com": "notice",
  "ftnremind_admin@qq.com": "notice",
  "no-reply@github.com": "notice",
  // 招聘 / 校园
  "zmedu@xwx.gzzmedu.com": "job",
  "cnpczhaopin-service6@cnpc.com.cn": "job",
  "cgn@mail.hrtools.cn": "job",
  "cv@service.bosszhipin.com": "job",
  "cg@npubu.cn": "job",
  "3364809295@qq.com": "job",
  "messages-noreply@linkedin.com": "job",
  // 广告农场（成批的贷款/征信/申卡群发）
  "spread@doubtless.guangmail.com": "spam",
  "anyihua@yuue.cgbcosnews.com": "spam",
  "outdated@redesign.meisilah.com": "spam",
  "barge@clockwise.cmbpost.com": "spam",
  "entrenched@scholastic.financesent.com": "spam",
  "sincerely@trustworthy.potestuser.com": "spam",
  "zaigan@zhuandsfggzhen.com": "spam",
  "celtic@fodde.welfaremail.com": "spam",
  "peanut@letter.plpyq.com": "spam",
  "online@place.cosemail.cn": "spam",
  "addien@partners.goai.xin": "spam",
  "desrb@xrdxc.sdzrz.com": "spam",
  "noreply@gift.meaput.com": "spam",
  "caiziqiaseng@zhuwsaentao.com": "spam",
};

// ---------------------------------------------------------------- 强身份域
const DOM = {
  acad: [
    "mail.tsinghua.edu.cn", "mail.scut.edu.cn", "scut.edu.cn", "unc.edu", "epa.gov",
    "smail.xtu.edu.cn", "xtu.edu.cn", "manuscriptcentral.com", "editorialmanager.com",
    "acspubs.org", "igsnrr.ac.cn", "lzb.ac.cn", "eiafans.com", "utk.edu",
    "elsevier.com", "springer.com", "wiley.com", "tandfonline.com", "crossref.org",
    "semanticscholar.org", "zotero.org", "ecmwf.int", "ourresearch.org",
  ],
  game: [
    "steampowered.com", "humblebundle.com", "rockstargames.com", "e.ea.com",
    "kleimail.com", "nexusmods.com", "2game.hk", "riotgames.com", "wbgames.com",
    "ubisoft.com", "epicgames.com", "battle.net", "xbox.com", "gog.com",
    "jmcomic.me", "yysls.cn", "techland.net", "cyberpunk.net", "avalanchestudios.com",
  ],
  work: ["hycx-gd.cn", "ciestgd.com"],
  job: ["shmail.ibeisen.com", "cnpc.com.cn", "mail.hrtools.cn", "saikr.com", "linkedin.com", "gzzmedu.com", "bosszhipin.com"],
  spam: ["guangmail.com", "cgbcosnews.com", "meisilah.com", "cmbpost.com", "financesent.com", "potestuser.com", "zhuandsfggzhen.com", "welfaremail.com", "plpyq.com", "cosemail.com", "goai.xin", "sdzrz.com", "meaput.com", "zhuwsaentao.com"],
  notice: ["npmjs.com", "microsoft.com", "infomail.microsoft.com", "system.trae.ai", "github.com", "axure.com", "google.com", "nasa.gov", "qq.com", "spcloud.cc", "xn--4gq62f.com", "sms-activate.org", "telegram.org"],
  promo: [
    "qoder.com", "sc.mail.deepseek.com", "tc.mail.deepseek.com", "info.vercel.com",
    "openrouter.ai", "tavily.com", "napkin.ai", "mail.trae.ai", "edmsend.csdn.net",
    "edx.org", "anaconda.com", "try.anaconda.com", "brave.com", "zoogvpn.com",
    "zoogvpnofficial.com.cn", "adguard-vpn.com", "adguard.com", "amap.com", "autonavi.com",
    "xshell.com", "m.xiaomi.com", "error.xiaomi.com", "xiaomi.com", "cgx.dev",
    "browseract.com", "typesafe.ai", "drex-usa.com", "mcpcnserver.com", "tencent.com",
    "996cloud.xyz", "ncdc.ac.cn", "qwenlm.ai", "doctranslator.com", "mused.org",
    "driffle.email", "xiaoshishiss.com", "amb56.com", "email.z.ai", "z.ai",
    "4399mail.com", "1delivery.re", "zlib-notifier.tech", "z-lib.gs", "z-lib.sh",
    "z-library.su", "z-library.online", "viewturbo.com", "sov5.com", "python88.com",
    "openclawmp.cc", "journals.email.elsevier.com", "csdn.net", "mused.com",
    "docker.com", "vercel.com",
  ],
};

// ---------------------------------------------------------------- 关键词
const RX = {
  ci: /Run (failed|completed)|workflow run|Workflow/i,
  githubCollab: /\[[\w./-]+\]\s+(Issue|PR|Pull request|Discussion)|Re: \[[\w./-]+\]|(Issue|PR) #\d+/i,
  auth: /验证码|驗證碼|驗証碼|验证代码|验证邮件|验证您的|verification|one-time code|一次性代码|your code|sign up code|verify email|verify your|登录代码|登录行为|登录提醒|登录详情|异地登录|安全提醒|安全警报|安全代码|帐户的安全|安全验证|密码|password|confirm your email|sign in|sign-in|login link|确认码|确认登录|确认你的电邮|新电脑|新设备|设备验证|请验证|申诉验证|账号申诉|激活你的|activate your|Account activation|reset your|重置|恢复您的账户|恢复您的帐户|修改邮箱|绑定邮箱/i,
  money: /工资|发票|账单|报销|扣款|退款|invoice|order|订单|收据|续费|续订失败|付款|支付|购买|Purchase/i,
  acad: /审稿|投稿|期刊|稿件|manuscript|paper review|co-author|reviewer|Editorial|会议|注册费|论文|thesis|课题组|数据集|AQAG|CAMx|DeepRSM|Model-VAT|学术/i,
  job: /招聘|应聘|申请我公司职位|简历|面试|笔试|offer|竞赛|大赛|挑战赛|校园|校招|招生|求职/i,
  game: /Steam|愿望单|願望單|特卖|特賣|特促|Humble|游戏|游戲|Social Club|Xbox|联机|赛季/i,
  spam: /\(AD\)|（AD）|申卡|额度|征信|专属福利|尊享|优享权益|荣誉名单|申请名单|福利已发|pos机|催收|放款|无抵押|秒批/i,
  notice: /域名变更|线路变更|服务条款|条款|隐私|政策变更|平台公告|服务通知|服务提醒|到期提醒|流量已达|已用流量/i,
  promo: /订阅|Subscri|newsletter|Weekly|简报|周报|优惠|折扣|免费|领取|邀请|活动|上新|发布计划|调价|续订|升级|试用|Beta|launch|webinar|survey|里程碑|激励计划|月报|欢迎注册|注册成功/i,
};

const domOf = (addr) => (addr.includes("@") ? addr.split("@").pop() : "");
// 按域边界匹配：mailer.humblebundle.com 命中 humblebundle.com，fakehumblebundle.com 不命中
const hasDom = (addr, list) => {
  const d = domOf(addr);
  return list.some((x) => addr === x || d === x || d.endsWith("." + x));
};

/**
 * 带“把握度”的判定。
 *   src = "strong" ：精确发件人 / 强身份域 / CI 与非 CI 的 GitHub 三分 / 强安全信号 —— 规则说了算，不必问模型
 *   src = "medium" ：主题关键词命中 —— 基本可靠，仍由规则接管
 *   src = "weak"   ：只靠营销关键词或弱域名 —— 交给 Jev 复核
 *   src = "none"   ：完全没命中（other）—— 交给 Jev 判
 * 只有 weak / none 才值得花模型钱。
 */
export function classifyDetail(m) {
  const addr = (m.from.match(/<([^>]+)>/)?.[1] || m.from || "").toLowerCase();
  const subj = m.subject || "";
  const S = (key, src) => ({ key, src });

  if (addr === SELF) return S("daily", "strong");

  // 1) 精确发件人（盘点时逐条确认过的）
  if (SENDERS[addr]) return S(SENDERS[addr], "strong");

  // 1.5) 真人找你办事 → 重要邮件
  //      （老师让你审稿、合作者发数据、HR 直接约面试，都会被这里捞出来）
  if (PEOPLE.has(addr)) return S("important", "strong");
  if (!RX_BULK.test(addr) && RX_DIRECT.test(subj)) return S("important", "medium");

  // 2) GitHub 三分：CI / 项目讨论 / 其他通知
  if (addr === "notifications@github.com") {
    if (RX.ci.test(subj)) return S("ci", "strong");
    if (RX.githubCollab.test(subj)) return S("work", "strong");
    return S("notice", "medium");
  }

  // 3) 强安全信号：账号类优先于“这封是谁发的”
  //    （Jev 对照实验发现：自家 Gitea 的「恢复您的账户」、GitHub 的 OAuth/Token 告警
  //      被域规则误分到 工作项目/平台通知，而这些本质是账号安全类）
  if (/恢复您的账户|恢复您的帐户|password|reset your|personal access token|OAuth|signed in|new sign-in|secrets detected|exposed on GitHub|修改邮箱|绑定邮箱/i.test(subj)) {
    return S("auth", "strong");
  }

  // 4) 强身份域
  if (hasDom(addr, DOM.acad)) return S("acad", "strong");
  if (hasDom(addr, DOM.game)) return S("game", "strong");
  if (hasDom(addr, DOM.work)) return S("work", "strong");
  if (hasDom(addr, DOM.job)) return S("job", "strong");
  if (hasDom(addr, DOM.spam)) return S("spam", "strong");

  // 5) 主题关键词（顺序即优先级）
  if (RX.auth.test(subj)) return S("auth", "medium");
  if (RX.spam.test(subj)) return S("spam", "medium"); // 诈骗群发里常带“订单/福利”字样，必须排在 money 前面
  if (RX.money.test(subj)) return S("money", "medium");
  if (RX.acad.test(subj)) return S("acad", "medium");
  if (RX.job.test(subj)) return S("job", "medium");
  if (RX.game.test(subj)) return S("game", "medium");
  if (RX.notice.test(subj)) return S("notice", "medium");

  // 6) 域名（弱信号放最后）
  if (hasDom(addr, DOM.notice)) return S("notice", "weak");
  if (hasDom(addr, DOM.promo)) return S("promo", "weak");
  if (RX.promo.test(subj)) return S("promo", "weak");
  return S("other", "none");
}

export function classify(m) {
  return classifyDetail(m).key;
}

/** 规则没把握、值得问模型的那批 */
export function needsModel(detail) {
  return detail.src === "weak" || detail.src === "none";
}
