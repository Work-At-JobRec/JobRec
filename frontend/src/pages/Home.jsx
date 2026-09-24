import Navbar from "../components/Navbar.jsx";

export default function Home() {
  return (
    <div className="flex flex-col items-center min-h-screen text-center">
      <Navbar />
      <div className="text-[96px] font-bold text-black mt-20 mb-5">JobRec</div>
      <div className="text-[22px] max-w-[800px] text-black mb-[30px] leading-relaxed">
        The applicant-focused job board you didn't know you needed!
      </div>
      <div className="text-[15px] text-black">
        Sharvari Deshpande, Luna Brown, Luke McCartney, and Pranav Putta
      </div>
    </div>
  );
}
