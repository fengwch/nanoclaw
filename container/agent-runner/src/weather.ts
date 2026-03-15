/**
 * Weather lookup for MCP get_weather tool.
 * Uses Open-Meteo (geocoding + forecast). Injectable fetch for testing.
 */

import https from 'https';

const WEATHER_USER_AGENT = 'NanoClaw-Weather/1.0 (https://github.com/nanoclaw)';

export type WeatherResult =
  | { content: Array<{ type: 'text'; text: string }>; isError?: false }
  | { content: Array<{ type: 'text'; text: string }>; isError: true };

export function createHttpsGet(timeoutMs: number): (url: string) => Promise<string> {
  return (url: string) =>
    new Promise((resolve, reject) => {
      const req = https.get(
        url,
        { headers: { 'User-Agent': WEATHER_USER_AGENT } },
        (res) => {
          if (res.statusCode !== 200) {
            reject(new Error(`HTTP ${res.statusCode}`));
            return;
          }
          const chunks: Buffer[] = [];
          res.on('data', (chunk: Buffer) => chunks.push(chunk));
          res.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
          res.on('error', reject);
        },
      );
      req.on('error', reject);
      req.setTimeout(timeoutMs, () => {
        req.destroy();
        reject(new Error('Request timeout'));
      });
    });
}

const CODE_TO_TEXT: Record<number, string> = {
  0: '晴',
  1: '大部晴朗',
  2: '少云',
  3: '多云',
  45: '雾',
  48: '雾凇',
  51: '毛毛雨',
  53: '毛毛雨',
  55: '毛毛雨',
  61: '小雨',
  63: '中雨',
  65: '大雨',
  71: '小雪',
  73: '中雪',
  75: '大雪',
  80: '小阵雨',
  81: '阵雨',
  82: '大阵雨',
  85: '小阵雪',
  86: '大阵雪',
  95: '雷暴',
  96: '雷暴伴小冰雹',
  99: '雷暴伴大冰雹',
};

/**
 * Fetch current weather for a city. Uses Open-Meteo (no API key).
 * @param city - City or location name (e.g. "Beijing", "上海")
 * @param getUrl - Function to perform HTTP GET and return response body (inject for tests)
 */
export async function fetchWeatherForCity(
  city: string,
  getUrl: (url: string) => Promise<string>,
): Promise<WeatherResult> {
  const trimmed = typeof city === 'string' ? city.trim() : String(city ?? '').trim();
  if (!trimmed) {
    return {
      content: [{ type: 'text', text: '请提供城市或地点名称，例如：北京、上海、Tokyo。' }],
      isError: true,
    };
  }

  const GEOCODE_URL = 'https://geocoding-api.open-meteo.com/v1/search';
  const WEATHER_URL = 'https://api.open-meteo.com/v1/forecast';

  try {
    const geoBody = await getUrl(
      `${GEOCODE_URL}?name=${encodeURIComponent(trimmed)}&count=1&language=zh`,
    );
    const geo = JSON.parse(geoBody) as {
      results?: Array<{
        latitude: number;
        longitude: number;
        name: string;
        admin1?: string;
        country_code?: string;
      }>;
    };
    const loc = geo.results?.[0];
    if (!loc) {
      return {
        content: [
          {
            type: 'text',
            text: `未找到地点「${trimmed}」。请换一个名称或加上国家（如「北京, 中国」）。`,
          },
        ],
        isError: true,
      };
    }

    const weatherBody = await getUrl(
      `${WEATHER_URL}?latitude=${loc.latitude}&longitude=${loc.longitude}&current_weather=true`,
    );
    const w = JSON.parse(weatherBody) as {
      current_weather?: {
        temperature: number;
        weathercode: number;
        windspeed: number;
        winddirection?: number;
      };
    };
    const c = w.current_weather;
    if (!c) {
      return {
        content: [{ type: 'text', text: '未获取到当前天气数据，请稍后再试。' }],
        isError: true,
      };
    }

    const place = [loc.name, loc.admin1, loc.country_code].filter(Boolean).join(', ');
    const condition = CODE_TO_TEXT[c.weathercode] ?? `天气码 ${c.weathercode}`;

    const text = [
      `【${place}】当前天气`,
      `气温：${c.temperature}°C`,
      `天气：${condition}`,
      `风速：${c.windspeed} km/h`,
    ].join('\n');

    return { content: [{ type: 'text', text }] };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return {
      content: [
        {
          type: 'text',
          text: `天气查询失败：${msg}。请检查网络或稍后重试，或换一个城市名。`,
        },
      ],
      isError: true,
    };
  }
}
