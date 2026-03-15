import * as lark from '@larksuiteoapi/node-sdk';

import { ASSISTANT_NAME } from '../config.js';
import { readEnvFile } from '../env.js';
import { logger } from '../logger.js';
import {
  Channel,
  OnInboundMessage,
  OnChatMetadata,
  RegisteredGroup,
} from '../types.js';
import { registerChannel } from './registry.js';

export interface FeishuChannelOpts {
  onMessage: OnInboundMessage;
  onChatMetadata: OnChatMetadata;
  registeredGroups: () => Record<string, RegisteredGroup>;
  appId: string;
  appSecret: string;
}

export class FeishuChannel implements Channel {
  name = 'feishu';

  private client!: lark.Client;
  private connected = false;
  private botOpenId: string | undefined;

  private opts: FeishuChannelOpts;

  constructor(opts: FeishuChannelOpts) {
    this.opts = opts;
  }

  async connect(): Promise<void> {
    const { appId, appSecret } = this.opts;

    this.client = new lark.Client({ appId, appSecret });

    // Fetch bot's own open_id so we can detect our own messages
    try {
      const resp = await this.client.request({
        method: 'GET',
        url: 'https://open.feishu.cn/open-apis/bot/v3/info',
      });
      this.botOpenId = (resp as any)?.bot?.open_id;
      logger.info({ botOpenId: this.botOpenId }, 'Feishu bot info fetched');
    } catch (err) {
      logger.warn(
        { err },
        'Failed to fetch Feishu bot info, bot message detection may not work',
      );
    }

    const wsClient = new lark.WSClient({
      appId,
      appSecret,
      loggerLevel: lark.LoggerLevel.warn,
    });

    const eventDispatcher = new lark.EventDispatcher({}).register({
      'im.message.receive_v1': async (data: any) => {
        logger.info(
          {
            payloadKeys: data ? Object.keys(data) : [],
            hasMessage: !!(data?.message ?? data?.event?.message),
            hasEvent: !!data?.event,
            eventKeys: data?.event ? Object.keys(data.event) : [],
          },
          'Feishu event im.message.receive_v1 received',
        );
        await this.handleMessage(data);
      },
    });

    wsClient.start({ eventDispatcher });
    this.connected = true;
    const registeredCount = Object.keys(this.opts.registeredGroups()).length;
    logger.info(
      { appIdSuffix: appId?.slice(-4), registeredGroupsCount: registeredCount },
      'Feishu WebSocket connected, waiting for im.message.receive_v1',
    );
  }

  private async handleMessage(data: any): Promise<void> {
    // SDK may pass data as {event: {message, sender}} or directly as {message, sender}
    const msg = data?.message || data?.event?.message;
    const sender = data?.sender || data?.event?.sender;

    if (!msg) {
      logger.info(
        {
          payloadKeys: data ? Object.keys(data) : [],
          eventKeys: data?.event ? Object.keys(data.event) : [],
          eventType: data?.event?.type ?? data?.type ?? data?.schema,
          sample: data ? JSON.stringify(data).slice(0, 300) : '',
        },
        'Feishu handleMessage: no message in payload (wrong shape or other event?), skip',
      );
      return;
    }

    const chatId = msg.chat_id;
    const messageType = msg.message_type;
    const chatType = msg.chat_type;
    logger.info(
      { chatId, messageType, chatType, messageId: msg.message_id },
      'Feishu message received',
    );

    // Skip bot's own messages
    if (
      sender?.sender_id?.open_id &&
      sender.sender_id.open_id === this.botOpenId
    ) {
      logger.info(
        {
          chatId,
          senderOpenId: sender.sender_id.open_id,
          botOpenId: this.botOpenId,
        },
        'Feishu handleMessage: skip bot own message',
      );
      return;
    }

    if (!chatId) {
      logger.warn(
        { messageId: msg.message_id, msgKeys: msg ? Object.keys(msg) : [] },
        'Feishu handleMessage: no chat_id in message, skip',
      );
      return;
    }

    const chatJid = `${chatId}@feishu`;
    const timestamp = new Date(Number(msg.create_time)).toISOString();
    const isGroup = chatType === 'group';

    // Always persist chat metadata so unregistered groups appear in chats table (for manual registration)
    this.opts.onChatMetadata(chatJid, timestamp, undefined, 'feishu', isGroup);
    logger.info(
      { chatJid, isGroup },
      'Feishu chat metadata stored (chats table)',
    );

    // Only handle text messages for delivery
    if (messageType !== 'text') {
      logger.info(
        { chatJid, messageType, chatType },
        'Feishu handleMessage: non-text message, skip delivery (chat metadata already stored)',
      );
      return;
    }

    let content = '';
    try {
      const parsed = JSON.parse(msg.content || '{}');
      content = parsed.text || '';
    } catch (e) {
      logger.warn(
        {
          chatJid,
          contentPreview: String(msg.content).slice(0, 100),
          err: (e as Error).message,
        },
        'Feishu handleMessage: failed to parse content JSON, skip',
      );
      return;
    }
    if (!content) {
      logger.info(
        { chatJid },
        'Feishu handleMessage: empty text content after parse, skip',
      );
      return;
    }

    const senderName = sender?.sender_id?.open_id || 'unknown';

    // Deliver message if group is registered
    const groups = this.opts.registeredGroups();
    if (groups[chatJid]) {
      this.opts.onMessage(chatJid, {
        id: msg.message_id || '',
        chat_jid: chatJid,
        sender: sender?.sender_id?.open_id || '',
        sender_name: senderName,
        content,
        timestamp,
        is_from_me: false,
        is_bot_message: false,
      });
    } else {
      const registeredJids = Object.keys(this.opts.registeredGroups());
      logger.info(
        {
          chatJid,
          contentLen: content.length,
          registeredCount: registeredJids.length,
          registeredJidsSample: registeredJids.slice(0, 3),
        },
        'Feishu message from unregistered group (not delivered to agent)',
      );
    }
  }

  async sendMessage(jid: string, text: string): Promise<void> {
    const chatId = jid.replace(/@feishu$/, '');
    const prefixed = `${ASSISTANT_NAME}: ${text}`;
    try {
      await this.client.im.v1.message.create({
        params: { receive_id_type: 'chat_id' },
        data: {
          receive_id: chatId,
          msg_type: 'text',
          content: JSON.stringify({ text: prefixed }),
        },
      });
      logger.info({ jid, length: prefixed.length }, 'Feishu message sent');
    } catch (err) {
      logger.error({ jid, err }, 'Failed to send Feishu message');
    }
  }

  isConnected(): boolean {
    return this.connected;
  }

  ownsJid(jid: string): boolean {
    return jid.endsWith('@feishu');
  }

  async disconnect(): Promise<void> {
    this.connected = false;
  }
}

registerChannel('feishu', (opts) => {
  const env = readEnvFile(['FEISHU_APP_ID', 'FEISHU_APP_SECRET']);
  const appId = env['FEISHU_APP_ID'];
  const appSecret = env['FEISHU_APP_SECRET'];

  if (!appId || !appSecret) {
    logger.debug(
      'Feishu not configured (FEISHU_APP_ID/FEISHU_APP_SECRET missing), skipping',
    );
    return null;
  }

  return new FeishuChannel({ ...opts, appId, appSecret });
});
