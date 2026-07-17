import dayjs, { Dayjs } from 'dayjs';
import 'dayjs/locale/zh-cn';

dayjs.locale('zh-cn');

export const roundToNextFiveMinutes = () => {
  const now = dayjs().add(1, 'hour');
  const minute = Math.ceil(now.minute() / 5) * 5;
  return now.minute(minute).second(0).millisecond(0);
};

export const toPayloadDateTime = (value: string) => {
  return value || null;
};

export const toPickerValue = (value: string) => {
  if (!value) return null;
  const date = dayjs(value);
  return date.isValid() ? date : null;
};

export const isPastDateTime = (value: string) => {
  const date = toPickerValue(value);
  return Boolean(date && date.isBefore(dayjs()));
};

export const disabledPastDate = (current: Dayjs) => {
  return current.endOf('day').isBefore(dayjs());
};

export const disabledPastTime = (current: Dayjs | null) => {
  if (!current || !current.isSame(dayjs(), 'day')) {
    return {};
  }

  const now = dayjs();
  return {
    disabledHours: () => Array.from({ length: now.hour() }, (_, hour) => hour),
    disabledMinutes: (selectedHour: number) => (
      selectedHour === now.hour()
        ? Array.from({ length: now.minute() + 1 }, (_, minute) => minute)
        : []
    ),
  };
};

export const formatDateTime = (value?: string | null) => {
  if (!value) return '未设置';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '未设置';
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
};

export const formatCountdownSeconds = (seconds: number) => {
  const safeSeconds = Math.max(0, seconds);
  const minutes = Math.floor(safeSeconds / 60);
  const remainingSeconds = safeSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`;
};
