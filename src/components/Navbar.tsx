
import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Menu } from "lucide-react";

const Navbar = () => {
  const [isScrolled, setIsScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Change navbar style on scroll
  useEffect(() => {
    const handleScroll = () => {
      if (window.scrollY > 10) {
        setIsScrolled(true);
      } else {
        setIsScrolled(false);
      }
    };

    window.addEventListener("scroll", handleScroll);
    return () => {
      window.removeEventListener("scroll", handleScroll);
    };
  }, []);

  const navLinks = [
    { title: "Features", href: "#features" },
    { title: "Benefits", href: "#benefits" },
    { title: "Testimonials", href: "#testimonials" },
  ];

  return (
    <nav className={`fixed top-0 w-full z-50 transition-all duration-300 ${isScrolled ? "bg-white shadow-md py-2" : "bg-transparent py-4"}`}>
      <div className="container px-4 md:px-6 mx-auto flex justify-between items-center">
        <a href="#" className="text-swb-green font-poppins font-bold text-2xl">
          Bingiene
        </a>

        {/* Desktop Menu */}
        <div className="hidden md:flex items-center space-x-8">
          <div className="flex items-center space-x-6">
            {navLinks.map(link => (
              <a 
                key={link.title} 
                href={link.href} 
                className="text-swb-dark-gray hover:text-swb-green transition-colors font-medium"
              >
                {link.title}
              </a>
            ))}
          </div>
          <Button 
            className="bg-swb-green hover:bg-swb-green/90"
            onClick={() => window.location.href="#features"}
          >
            Learn More
          </Button>
        </div>

        {/* Mobile Menu Button */}
        <div className="md:hidden">
          <Button 
            variant="ghost" 
            size="icon" 
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          >
            <Menu size={24} />
          </Button>
        </div>
      </div>

      {/* Mobile Menu */}
      {mobileMenuOpen && (
        <div className="md:hidden bg-white shadow-lg absolute w-full">
          <div className="container px-4 py-4 flex flex-col space-y-4">
            {navLinks.map(link => (
              <a 
                key={link.title} 
                href={link.href} 
                className="text-swb-dark-gray hover:text-swb-green py-2 transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                {link.title}
              </a>
            ))}
            <Button 
              className="bg-swb-green hover:bg-swb-green/90 w-full"
              onClick={() => {
                window.location.href="#features";
                setMobileMenuOpen(false);
              }}
            >
              Learn More
            </Button>
          </div>
        </div>
      )}
    </nav>
  );
};

export default Navbar;
