import Autopilot from "../components/Autopilot";
import useWorkspace from "../hooks/useWorkspace";

export default function AutopilotPage() {
  const { facebookConnected, pageName, onPublished, refreshActivity } = useWorkspace();

  return (
    <Autopilot
      facebookConnected={facebookConnected}
      pageName={pageName}
      onDone={(kind) => (kind === "published" ? onPublished() : refreshActivity())}
    />
  );
}
