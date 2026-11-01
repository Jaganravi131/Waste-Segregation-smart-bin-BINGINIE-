
import React from "react";
import { cn } from "@/lib/utils";

interface SectionContainerProps {
  children: React.ReactNode;
  className?: string;
  id?: string;
}

const SectionContainer: React.FC<SectionContainerProps> = ({ 
  children, 
  className,
  id 
}) => {
  return (
    <section
      id={id}
      className={cn(
        "w-full py-16 md:py-24",
        className
      )}
    >
      <div className="container px-4 md:px-6">
        {children}
      </div>
    </section>
  );
};

export default SectionContainer;
