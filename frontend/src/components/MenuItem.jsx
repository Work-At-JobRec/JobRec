export default function MenuItem({ label }) {
  return (
    <div className="flex items-center gap-4 my-[30px] text-2xl font-bold">
      <span className="w-[22px] h-[22px] border-[1.8px] border-[#444] rounded-full inline-flex items-center justify-center text-base text-[#444] shrink-0">
        +
      </span>
      <span>{label}</span>
    </div>
  );
}
