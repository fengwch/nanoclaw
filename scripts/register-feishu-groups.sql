-- 注册飞书群组到 chats 和 registered_groups
-- 执行: sqlite3 store/messages.db < scripts/register-feishu-groups.sql

-- 群1: oc_d639f899612e77173bc928708e1b123d
INSERT OR REPLACE INTO chats (jid, name, last_message_time, channel, is_group)
VALUES (
  'oc_d639f899612e77173bc928708e1b123d@feishu',
  '飞书群1',
  datetime('now'),
  'feishu',
  1
);
INSERT OR REPLACE INTO registered_groups (jid, name, folder, trigger_pattern, added_at, requires_trigger)
VALUES (
  'oc_d639f899612e77173bc928708e1b123d@feishu',
  '飞书群1',
  'feishu_group1',
  '@Andy',
  datetime('now'),
  1
);

-- 群2: oc_834aca937961626549c9c51ace8377b8
INSERT OR REPLACE INTO chats (jid, name, last_message_time, channel, is_group)
VALUES (
  'oc_834aca937961626549c9c51ace8377b8@feishu',
  '飞书群2',
  datetime('now'),
  'feishu',
  1
);
INSERT OR REPLACE INTO registered_groups (jid, name, folder, trigger_pattern, added_at, requires_trigger)
VALUES (
  'oc_834aca937961626549c9c51ace8377b8@feishu',
  '飞书群2',
  'feishu_group2',
  '@Andy',
  datetime('now'),
  1
);
