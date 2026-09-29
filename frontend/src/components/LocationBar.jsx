import { useState } from "react";
import { PinIcon } from "./Icons.jsx";

export default function LocationBar() {
  const [location, setLocation] = useState("West Lafayette, IN");
  const [radius, setRadius] = useState(10);

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-3 text-[22px]">
      <label htmlFor="location" className="font-bold">
        Change Location:
      </label>
      <div className="flex items-center border-[1.5px] border-black rounded-full px-3 py-0.5 w-[280px]">
        <input
          id="location"
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          className="flex-1 min-w-0 bg-transparent outline-none"
        />
        <PinIcon className="w-5 h-5 shrink-0" />
      </div>
      <label htmlFor="radius" className="font-bold ml-4">
        Radius:
      </label>
      <input
        id="radius"
        type="number"
        min="1"
        value={radius}
        onChange={(e) => setRadius(e.target.value)}
        className="border-[1.5px] border-black rounded-full px-3 py-0.5 w-[104px] text-right outline-none"
      />
      <span>miles</span>
    </div>
  );
}
