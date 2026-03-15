/**
 * Unit + integration tests for weather MCP (get_weather).
 * Run: npm test
 * Integration test (real Open-Meteo API) runs by default; set SKIP_WEATHER_INTEGRATION=1 to skip.
 */

import { describe, it, expect } from 'vitest';
import {
  fetchWeatherForCity,
  createHttpsGet,
  type WeatherResult,
} from './weather.js';

const GEO_RESPONSE = JSON.stringify({
  results: [
    {
      latitude: 39.9075,
      longitude: 116.39723,
      name: '北京市',
      admin1: '北京',
      country_code: 'CN',
    },
  ],
});

const WEATHER_RESPONSE = JSON.stringify({
  current_weather: {
    temperature: 12.5,
    weathercode: 0,
    windspeed: 6.3,
    winddirection: 193,
  },
});

describe('fetchWeatherForCity', () => {
  it('returns error when city is empty', async () => {
    const getUrl = async () => '';
    const result = await fetchWeatherForCity('  ', getUrl);
    expect(result.isError).toBe(true);
    expect(result.content[0].text).toContain('请提供城市或地点名称');
  });

  it('returns error when geocoding has no results', async () => {
    const getUrl = async (url: string) => {
      if (url.includes('geocoding-api')) return JSON.stringify({ results: [] });
      return WEATHER_RESPONSE;
    };
    const result = await fetchWeatherForCity('NowhereXyZ', getUrl);
    expect(result.isError).toBe(true);
    expect(result.content[0].text).toMatch(/未找到地点/);
  });

  it('returns error when weather API returns no current_weather', async () => {
    const getUrl = async (url: string) => {
      if (url.includes('geocoding-api')) return GEO_RESPONSE;
      return JSON.stringify({});
    };
    const result = await fetchWeatherForCity('北京', getUrl);
    expect(result.isError).toBe(true);
    expect(result.content[0].text).toContain('未获取到当前天气数据');
  });

  it('returns error when getUrl throws', async () => {
    const getUrl = async () => {
      throw new Error('Network error');
    };
    const result = await fetchWeatherForCity('北京', getUrl);
    expect(result.isError).toBe(true);
    expect(result.content[0].text).toContain('天气查询失败');
    expect(result.content[0].text).toContain('Network error');
  });

  it('formats weather successfully with mocked API (unit)', async () => {
    const getUrl = async (url: string) => {
      if (url.includes('geocoding-api')) return GEO_RESPONSE;
      if (url.includes('forecast')) return WEATHER_RESPONSE;
      throw new Error('Unexpected URL');
    };
    const result = await fetchWeatherForCity('北京', getUrl);
    expect(result.isError).toBeFalsy();
    const text = (result as WeatherResult).content[0].text;
    expect(text).toContain('当前天气');
    expect(text).toContain('气温：12.5°C');
    expect(text).toContain('晴');
    expect(text).toContain('风速：6.3 km/h');
    expect(text).toMatch(/北京市|北京|CN/);
  });

  it('uses weathercode mapping for conditions', async () => {
    const getUrl = async (url: string) => {
      if (url.includes('geocoding-api')) return GEO_RESPONSE;
      return JSON.stringify({
        current_weather: { temperature: 5, weathercode: 61, windspeed: 10 },
      });
    };
    const result = await fetchWeatherForCity('上海', getUrl);
    expect(result.isError).toBeFalsy();
    expect((result as WeatherResult).content[0].text).toContain('小雨');
  });

  it('calls real Open-Meteo API and returns weather (integration)', async () => {
    if (process.env.SKIP_WEATHER_INTEGRATION === '1') {
      return;
    }
    const httpsGet = createHttpsGet(15_000);
    const result = await fetchWeatherForCity('Beijing', httpsGet);
    expect(result.isError).toBeFalsy();
    const text = (result as WeatherResult).content[0].text;
    // 输出返回的天气详情，便于确认接口调通
    console.log('\n--- 天气 MCP 集成测试返回 (Open-Meteo 真实调用) ---');
    console.log(text);
    console.log('--- 以上为 get_weather 返回内容 ---\n');
    expect(text).toContain('当前天气');
    expect(text).toContain('气温：');
    expect(text).toContain('°C');
    expect(text).toMatch(/晴|多云|少云|大部晴朗|天气码 \d+/);
    expect(text).toContain('风速：');
    expect(text).toContain('km/h');
  }, 20_000);
});
