
import { cn } from "@/lib/utils";

interface StatCardProps {
  statValue: string;
  statLabel: string;
  className?: string;
}

const StatCard = ({ statValue, statLabel, className }: StatCardProps) => {
  return (
    <div className={cn(
      "bg-white p-6 rounded-xl shadow-md text-center",
      className
    )}>
      <div className="text-3xl md:text-4xl font-bold text-swb-green mb-2">
        {statValue}
      </div>
      <p className="text-gray-600">{statLabel}</p>
    </div>
  );
};

export default StatCard;
