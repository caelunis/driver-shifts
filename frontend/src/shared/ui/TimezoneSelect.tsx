import { forwardRef, useMemo, type SelectHTMLAttributes } from "react";

import { allZones, KZ_ZONES, zoneLabel } from "@/shared/lib/timezones";

/** IANA zones, Kazakhstan's first. */
export const TimezoneSelect = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  function TimezoneSelect(props, ref) {
    const rest = useMemo(allZones, []);
    return (
      <select ref={ref} {...props}>
        <optgroup label="Казахстан">
          {KZ_ZONES.map((z) => (
            <option key={z} value={z}>
              {zoneLabel(z)}
            </option>
          ))}
        </optgroup>
        <optgroup label="Все часовые пояса">
          {rest.map((z) => (
            <option key={z} value={z}>
              {zoneLabel(z)}
            </option>
          ))}
        </optgroup>
      </select>
    );
  },
);
