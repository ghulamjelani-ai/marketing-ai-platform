import AutoPoster from "../components/AutoPoster";
import useWorkspace from "../hooks/useWorkspace";

export default function WeekPlan() {
  const { facebookConnected, pageName, activity, refreshActivity } = useWorkspace();

  return (
    <AutoPoster
      facebookConnected={facebookConnected}
      pageName={pageName}
      upcoming={activity.upcoming}
      past={activity.past}
      onChanged={refreshActivity}
    />
  );
}
