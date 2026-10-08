// Server error codes -> Russian text. The server sends stable codes plus English
// messages; the English message is the fallback for codes not listed here.
import { formatMoney } from "@/shared/lib/money";
import { formatDateTime } from "@/shared/lib/time";
import { ApiError } from "@/shared/api/client";
import type { FieldError } from "@/shared/api/types";

const num = (v: unknown) => (typeof v === "number" ? v : Number(v));

export function fieldErrorMessage(e: FieldError): string {
  const c = e.ctx;
  switch (e.code) {
    case "missing":
    case "null_not_allowed":
    case "blank":
      return "Заполните поле";
    case "greater_than":
      return `Должно быть больше ${c.gt}`;
    case "greater_than_equal":
      return `Не может быть меньше ${c.ge}`;
    case "less_than":
      return `Должно быть меньше ${c.lt}`;
    case "less_than_equal":
      return e.field === "amount" ? `Не больше ${formatMoney(num(c.le))}` : `Не больше ${c.le}`;
    case "string_too_short":
      return num(c.min_length) === 1 ? "Заполните поле" : `Не меньше ${c.min_length} символов`;
    case "string_too_long":
      return `Не больше ${c.max_length} символов`;
    case "int_parsing":
    case "int_type":
    case "int_from_float":
      return "Введите целое число";
    case "float_parsing":
    case "float_type":
      return "Введите число";
    case "datetime_parsing":
    case "datetime_type":
    case "datetime_from_date_parsing":
      return "Укажите дату и время";
    case "literal_error":
    case "enum":
      return "Выберите значение из списка";
    case "value_error":
      return e.field === "email" ? "Некорректный e-mail" : e.message.replace(/^Value error, /, "");
    case "extra_forbidden":
      return "Неизвестное поле";
    case "timezone_required":
      return "Укажите часовой пояс";
    case "unknown_timezone":
      return "Неизвестный часовой пояс";
    case "invalid_characters":
      return "Недопустимые символы";
    case "name_without_letters":
      return "Имя должно содержать буквы";
    case "invalid_plate":
      return "Номер в формате 123 ABC 02";
    case "password_like_email":
      return "Пароль не должен совпадать с e-mail";
    case "password_too_common":
      return "Слишком простой пароль";
    case "end_before_start":
      return "Окончание должно быть позже начала";
    case "trip_too_short":
      return "Поездка длится не меньше минуты";
    case "trip_too_long":
      return "Поездка длится не больше 6 часов";
    case "commission_exceeds_amount":
      return "Комиссия должна быть меньше суммы";
    case "commission_fixed":
      return `Комиссию считает сервер: ${formatMoney(num(c.expected))}`;
    case "shift_not_found":
      return "Смена не найдена";
    case "outside_shift":
      return e.field === "start" ? "Поездка начинается раньше смены" : "Поездка заканчивается после смены";
    case "in_future":
      return "Это время ещё не наступило";
    case "too_old":
      return "Можно вносить не старше 7 дней";
    case "shift_too_long":
      return "Смена длится не больше 24 часов";
    case "before_last_trip":
      return `Смена не может закончиться раньше последней поездки (${formatDateTime(String(c.last_trip_end))})`;
    case "after_first_trip":
      return `Смена не может начаться позже первой поездки (${formatDateTime(String(c.first_trip_start))})`;
    case "start_required":
      return "Укажите начало";
    default:
      return e.message;
  }
}

/** Text for an error that is not about one field: 401, 403, 404, 409, 429, 5xx. */
export function errorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) return "Что-то пошло не так";
  switch (err.code) {
    case "network_error":
      return "Сервер недоступен, проверьте соединение";
    case "invalid_credentials":
      return "Неверный e-mail или пароль";
    case "too_many_attempts":
      return `Слишком много попыток. Попробуйте через ${Math.ceil(num(err.ctx.retry_after) / 60)} мин.`;
    case "not_authenticated":
      return "Сессия истекла, войдите снова";
    case "shift_already_open":
      return "Уже есть открытая смена — сначала закончите её";
    case "shift_already_closed":
      return "Смена уже закончена";
    case "shift_overlap":
      return "Пересекается с другой сменой";
    case "shift_locked":
      return "Смена закончилась больше 7 дней назад — изменить её может только администратор";
    case "trip_overlap":
      return "Пересекается с другой поездкой";
    case "trip_conflict":
      return "Поездка с таким id уже есть, но с другими данными";
    case "trip_changed":
      return "Поездку только что изменили — попробуйте ещё раз";
    case "email_taken":
      return "Этот e-mail уже зарегистрирован";
    case "plate_taken":
      return "Этот номер уже у другого водителя";
    case "not_found":
    case "driver_not_found":
      return "Не найдено — возможно, уже удалено";
    case "validation_error":
      return err.fields.map(fieldErrorMessage).join("; ");
    default:
      return err.status >= 500 ? `Ошибка сервера (${err.status})` : err.message;
  }
}
