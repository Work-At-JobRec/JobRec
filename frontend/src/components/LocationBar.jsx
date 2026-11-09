import { PinIcon } from "./Icons.jsx";

// City or region text search. Jobs and Search decide when to apply the filter.
// A mileage radius would require coordinates, which job listings don't currently provide.
export default function LocationBar({ location, onLocationChange, placeholder = "City, State (e.g. Chicago, IL)" }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-3 text-[22px]">
      <label htmlFor="location" className="font-bold">
        Location:
      </label>
      <div className="flex items-center border-[1.5px] border-black rounded-full px-3 py-0.5 w-[280px]">
        <input
          id="location"
          type="search"
          value={location}
          placeholder={placeholder}
          onChange={(e) => onLocationChange(e.target.value)}
          className="flex-1 min-w-0 bg-transparent outline-none"
        />
        <PinIcon className="w-5 h-5 shrink-0" />
      </div>
    </div>
  );
}
