
import { cn } from "@/lib/utils";
import { LucideIcon } from "lucide-react";

interface FeatureCardProps {
  title: string;
  description: string;
  icon: LucideIcon;
  className?: string;
}

const FeatureCard = ({ title, description, icon: Icon, className }: FeatureCardProps) => {
  return (
    <div className={cn(
      "bg-white p-6 rounded-xl shadow-md transition-all duration-300 hover:shadow-lg hover:-translate-y-1",
      className
    )}>
      <div className="w-12 h-12 mb-4 bg-swb-light-green rounded-lg flex items-center justify-center text-swb-green">
        <Icon size={24} />
      </div>
      <h3 className="text-xl font-semibold mb-2 text-swb-dark-gray">{title}</h3>
      <p className="text-gray-600">{description}</p>
    </div>
  );
};

export default FeatureCard;
