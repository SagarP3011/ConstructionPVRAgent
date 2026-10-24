import { Header } from "./components/layout/Header";
import { RoomLayout } from "./components/layout/RoomLayout";

export default function App() {
  return (
    <div className="flex h-full min-w-[1280px] flex-col">
      <Header />
      <RoomLayout />
    </div>
  );
}
