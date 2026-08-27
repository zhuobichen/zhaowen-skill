import { logger } from './logger.js';
import type { PendingPermission } from './session.js';
import { loadConfig } from './config.js';
import { existsSync } from 'node:fs';
import { statSync } from 'node:fs';

const PERMISSION_TIMEOUT = 60_000;

// 记录会话期间创建的文件（用于判断"新文件"）
const createdFiles = new Set<string>();

// 记录会话开始时间
const sessionStartTime = Date.now();

// 危险操作关键词列表
const DANGEROUS_PATTERNS = [
  // 强制递归删除 - 危险（除非在工作目录内）
  'rm -rf', 'rm -r f', 'rm -fr', 'rm -rf/',
  // 根目录删除 - 极度危险
  'rm /', 'rm /home', 'rm /usr', 'rm /etc', 'rm /bin', 'rm /sbin', 'rm /lib',
  'rm /root', 'rm /var', 'rm /opt', 'rm /tmp', 'rm /mnt', 'rm /media',
  'del /', 'del /home', 'del /usr', 'del /etc',
  // Windows 系统目录 - 极度危险
  '\\\\windows\\\\', '\\\\windows\\\\system32',
  'del \\\\windows', 'del \\\\system32',
  // 危险命令
  'dd if=', 'mkfs', 'mkswap',
  'shutdown', 'reboot', 'halt', 'poweroff',
  'deltree', 'deltree /',
  // 数据库危险操作
  'drop table', 'drop database', 'drop index', 'drop column',
  'truncate table', 'truncate',
  'delete from.*where', 'delete.* from .* --',
  // 危险脚本
  'eval.*base64', 'exec.*base64',
];

// 检查是否为危险操作（不考虑路径）
function isDangerousPattern(toolName: string, toolInput: string): boolean {
  const combined = `${toolName} ${toolInput}`.toLowerCase();
  for (const pattern of DANGEROUS_PATTERNS) {
    const regex = new RegExp(pattern, 'i');
    if (regex.test(combined)) {
      return true;
    }
  }
  return false;
}

// 归一化路径（统一路径分隔符，去除末尾斜杠）
function normalizePath(path: string): string {
  return path.replace(/\\/g, '/').replace(/\/+$/, '');
}

// 检查路径是否在工作目录下
function isPathInWorkingDirectory(path: string, workDir: string): boolean {
  const normalizedPath = normalizePath(path);
  const normalizedWorkDir = normalizePath(workDir);

  // 精确匹配
  if (normalizedPath.startsWith(normalizedWorkDir + '/')) {
    return true;
  }
  // 或者完全相等（针对目录）
  if (normalizedPath === normalizedWorkDir) {
    return true;
  }
  return false;
}

// 检查文件是否在会话期间创建的（新文件）
// 通过文件时间戳判断：如果文件的修改时间在会话开始之后，认为是新文件
function isNewlyCreatedFile(filePath: string): boolean {
  try {
    if (!existsSync(filePath)) return false;

    const stats = statSync(filePath);
    // mtime 是文件的修改时间
    const fileMtime = stats.mtime.getTime();
    // 会话开始时间 + 5分钟宽限期（考虑到可能的时钟偏差）
    const threshold = sessionStartTime - 5 * 60 * 1000;

    // 如果文件修改时间在会话开始后，认为是新文件
    if (fileMtime > threshold) {
      logger.info('File appears to be newly created', { filePath, fileMtime, sessionStartTime });
      return true;
    }
  } catch {
    // 忽略错误
  }
  return false;
}

// 检查是否为删除操作
function isDeleteOperation(toolName: string, toolInput: string): boolean {
  const combined = `${toolName} ${toolInput}`.toLowerCase();
  const deletePatterns = [
    /\brm\b/, /\bdel\b/, /\bdelete\b/, /\bremove\b/,
    /\bunlink\b/, /\brmdir\b/, /\brmdir\b/
  ];
  return deletePatterns.some(p => p.test(combined));
}

// 从命令输入中提取文件路径
function extractFilePaths(toolName: string, toolInput: string): string[] {
  const paths: string[] = [];

  // 简单的路径提取（处理常见的 rm/del 命令格式）
  // rm file1 file2
  // rm -rf directory
  // del file
  const normalizedInput = toolInput.replace(/\\/g, '/');

  // 匹配 rm/del/rmdir 等命令后面的路径
  // 处理 rm -rf /path, rm /path, del /path 等格式
  const pathPattern = /(?:rm|del|rmdir|delete|remove|unlink)\s+(?:-[a-z]+\s+)*([^\s]+)/gi;
  let match;
  while ((match = pathPattern.exec(normalizedInput)) !== null) {
    let path = match[1];
    // 去除引号
    path = path.replace(/^['"]|['"]$/g, '');
    // 跳过选项（如 -rf）
    if (path.startsWith('-')) continue;
    paths.push(path);
  }

  return paths;
}

// 注册创建的文件（供外部调用）
export function registerCreatedFile(filePath: string): void {
  createdFiles.add(normalizePath(filePath));
  logger.info('Registered created file', { filePath });
}

// 清除创建文件记录
export function clearCreatedFiles(): void {
  createdFiles.clear();
}

// 检查是否为只读/安全操作
function isSafeOperation(toolName: string): boolean {
  const safeTools = [
    'read', 'glob', 'grep', 'search', 'lsof', 'stat', 'exists',
    'taskl', 'tasklist', 'process-status',
    'web-fetch', 'web-search', 'mcp-resources',
    'ask', 'confirm',
    'bash',
  ];
  return safeTools.some(t => toolName.toLowerCase().includes(t));
}

export type OnPermissionTimeout = () => void;

export function createPermissionBroker(onTimeout?: OnPermissionTimeout) {
  const pending = new Map<string, PendingPermission>();

  function createPending(accountId: string, toolName: string, toolInput: string): Promise<boolean> {
    // 自动允许安全操作
    if (isSafeOperation(toolName)) {
      return Promise.resolve(true);
    }

    // 获取工作目录
    const config = loadConfig();
    const workDir = config.workingDirectory || process.cwd();

    // 如果是删除操作，检查路径
    if (isDeleteOperation(toolName, toolInput)) {
      const filePaths = extractFilePaths(toolName, toolInput);

      if (filePaths.length > 0) {
        let allInWorkDir = true;
        let hasNewFile = false;

        for (const filePath of filePaths) {
          const normalizedPath = normalizePath(filePath);

          // 如果路径是相对的，基于工作目录解析
          let fullPath = normalizedPath;
          if (!normalizedPath.startsWith('/') && !normalizedPath.match(/^[a-zA-Z]:/)) {
            fullPath = normalizePath(workDir + '/' + normalizedPath);
          }

          if (!isPathInWorkingDirectory(fullPath, workDir)) {
            allInWorkDir = false;
          }

          if (isNewlyCreatedFile(fullPath)) {
            hasNewFile = true;
          }
        }

        // 工作目录内的删除操作，或新创建的文件删除 -> 自动允许
        if (allInWorkDir || hasNewFile) {
          logger.info('Auto-allowing delete in workdir or new file', { toolName, filePaths });
          return Promise.resolve(true);
        }

        // 工作目录外的删除 -> 需要确认
        logger.info('Delete outside workdir requires permission', { toolName, filePaths });
      }
    }

    // 检查是否为危险模式（不考虑路径）
    if (isDangerousPattern(toolName, toolInput)) {
      // 危险操作，需要微信确认
      return new Promise<boolean>((resolve) => {
        logger.info('Dangerous operation requires permission', { accountId, toolName });
        const timer = setTimeout(() => {
          logger.warn('Permission timeout, auto-denied', { accountId, toolName });
          pending.delete(accountId);
          resolve(false);
          onTimeout?.();
        }, PERMISSION_TIMEOUT);

        pending.set(accountId, { toolName, toolInput, resolve, timer });
      });
    }

    // 其他非危险操作，自动允许
    return Promise.resolve(true);
  }

  function resolvePermission(accountId: string, allowed: boolean): boolean {
    const perm = pending.get(accountId);
    if (!perm) return false;
    clearTimeout(perm.timer);
    pending.delete(accountId);
    perm.resolve(allowed);
    logger.info('Permission resolved', { accountId, toolName: perm.toolName, allowed });
    return true;
  }

  function getPending(accountId: string): PendingPermission | undefined {
    return pending.get(accountId);
  }

  function formatPendingMessage(perm: PendingPermission): string {
    return [
      '🔧 权限请求',
      '',
      `工具: ${perm.toolName}`,
      `输入: ${perm.toolInput.slice(0, 500)}`,
      '',
      '回复 y 允许，n 拒绝',
      '(60秒未回复自动拒绝)',
    ].join('\n');
  }

  function rejectPending(accountId: string): boolean {
    const perm = pending.get(accountId);
    if (!perm) return false;
    clearTimeout(perm.timer);
    pending.delete(accountId);
    perm.resolve(false);
    logger.info('Permission auto-rejected', { accountId, toolName: perm.toolName });
    return true;
  }

  return { createPending, resolvePermission, rejectPending, getPending, formatPendingMessage };
}
