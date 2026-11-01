
import { cn } from "@/lib/utils";

interface TestimonialCardProps {
  quote: string;
  author: string;
  role: string;
  organization: string;
  className?: string;
}

const TestimonialCard = ({ 
  quote, 
  author, 
  role, 
  organization,
  className 
}: TestimonialCardProps) => {
  return (
    <div className={cn(
      "bg-white p-6 rounded-xl shadow-md",
      "flex flex-col justify-between",
      "border border-gray-100",
      className
    )}>
      <div>
        <div className="flex mb-4 text-yellow-400">
          {[...Array(5)].map((_, i) => (
            <svg key={i} xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
              <path d="M3.612 15.443c-.386.198-.824-.149-.746-.592l.83-4.73L.173 6.765c-.329-.314-.158-.888.283-.95l4.898-.696L7.538.792c.197-.39.73-.39.927 0l2.184 4.327 4.898.696c.441.062.612.636.282.95l-3.522 3.356.83 4.73c.078.443-.36.79-.746.592L8 13.187l-4.389 2.256z"/>
            </svg>
          ))}
        </div>
        <p className="italic text-gray-700 mb-4">"{quote}"</p>
      </div>
      <div>
        <p className="font-semibold">{author}</p>
        <p className="text-sm text-gray-500">{role}, {organization}</p>
      </div>
    </div>
  );
};

export default TestimonialCard;
