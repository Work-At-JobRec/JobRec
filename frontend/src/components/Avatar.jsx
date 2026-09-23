export default function Avatar({ editable = false }) {
  return (
    <div className="relative w-[132px] h-[132px] mx-auto mt-6 mb-[22px]">
      <div className="avatar relative w-[132px] h-[132px] rounded-full bg-[#b1b3b7]"></div>
      {editable && (
        <div className="absolute -right-0.5 bottom-2.5 w-7 h-7 rounded-full bg-white border-2 border-[#555] grid place-items-center text-[22px] leading-none text-[#555]">
          +
        </div>
      )}
    </div>
  );
}
