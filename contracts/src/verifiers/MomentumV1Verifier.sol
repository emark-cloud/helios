// SPDX-License-Identifier: GPL-3.0
/*
    Copyright 2021 0KIMS association.

    This file is generated with [snarkJS](https://github.com/iden3/snarkjs).

    snarkJS is a free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    snarkJS is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
    or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
    License for more details.

    You should have received a copy of the GNU General Public License
    along with snarkJS. If not, see <https://www.gnu.org/licenses/>.
*/

pragma solidity >=0.7.0 <0.9.0;

contract MomentumV1Verifier {
    // Scalar field size
    uint256 constant r =
        21_888_242_871_839_275_222_246_405_745_257_275_088_548_364_400_416_034_343_698_204_186_575_808_495_617;
    // Base field size
    uint256 constant q =
        21_888_242_871_839_275_222_246_405_745_257_275_088_696_311_157_297_823_662_689_037_894_645_226_208_583;

    // Verification Key data
    uint256 constant alphax =
        20_491_192_805_390_485_299_153_009_773_594_534_940_189_261_866_228_447_918_068_658_471_970_481_763_042;
    uint256 constant alphay =
        9_383_485_363_053_290_200_918_347_156_157_836_566_562_967_994_039_712_273_449_902_621_266_178_545_958;
    uint256 constant betax1 =
        4_252_822_878_758_300_859_123_897_981_450_591_353_533_073_413_197_771_768_651_442_665_752_259_397_132;
    uint256 constant betax2 =
        6_375_614_351_688_725_206_403_948_262_868_962_793_625_744_043_794_305_715_222_011_528_459_656_738_731;
    uint256 constant betay1 =
        21_847_035_105_528_745_403_288_232_691_147_584_728_191_162_732_299_865_338_377_159_692_350_059_136_679;
    uint256 constant betay2 =
        10_505_242_626_370_262_277_552_901_082_094_356_697_409_835_680_220_590_971_873_171_140_371_331_206_856;
    uint256 constant gammax1 =
        11_559_732_032_986_387_107_991_004_021_392_285_783_925_812_861_821_192_530_917_403_151_452_391_805_634;
    uint256 constant gammax2 =
        10_857_046_999_023_057_135_944_570_762_232_829_481_370_756_359_578_518_086_990_519_993_285_655_852_781;
    uint256 constant gammay1 =
        4_082_367_875_863_433_681_332_203_403_145_435_568_316_851_327_593_401_208_105_741_076_214_120_093_531;
    uint256 constant gammay2 =
        8_495_653_923_123_431_417_604_973_247_489_272_438_418_190_587_263_600_148_770_280_649_306_958_101_930;
    uint256 constant deltax1 =
        4_951_416_391_712_838_895_633_471_597_447_663_744_150_916_538_592_971_151_920_124_563_444_122_902_219;
    uint256 constant deltax2 =
        13_890_220_810_275_121_447_558_570_165_210_751_699_678_798_127_376_033_954_893_846_809_429_296_635_300;
    uint256 constant deltay1 =
        20_402_232_898_998_448_267_376_320_275_391_173_072_647_118_064_770_511_036_667_858_931_050_912_968_328;
    uint256 constant deltay2 =
        17_397_609_207_797_449_089_982_156_527_761_729_947_359_626_381_876_545_071_784_277_374_188_518_371_529;

    uint256 constant IC0x =
        5_796_926_967_072_684_761_624_520_576_751_878_864_269_797_299_454_850_185_999_419_070_622_997_685_833;
    uint256 constant IC0y =
        2_498_947_695_558_565_084_934_945_375_985_388_215_600_933_250_922_244_248_938_154_969_362_219_693_725;

    uint256 constant IC1x =
        21_146_677_028_910_938_053_727_494_868_506_835_373_162_652_806_830_999_396_572_161_174_025_800_240_771;
    uint256 constant IC1y =
        8_558_358_193_083_654_788_887_192_428_012_112_890_423_261_608_677_933_321_944_185_449_082_153_046_446;

    uint256 constant IC2x =
        4_554_876_679_305_662_303_093_763_286_742_219_617_598_255_550_915_686_153_239_935_386_462_179_458_792;
    uint256 constant IC2y =
        6_246_299_988_102_420_371_255_165_874_778_298_631_584_448_318_405_677_356_524_406_613_267_929_979_777;

    uint256 constant IC3x =
        19_715_900_016_689_916_977_380_953_436_369_194_226_003_325_755_847_110_283_521_009_434_093_185_752_587;
    uint256 constant IC3y =
        3_448_144_698_702_122_327_409_906_566_884_424_043_121_996_745_350_075_578_216_311_838_370_413_815_035;

    uint256 constant IC4x =
        11_046_872_790_675_995_231_891_333_834_134_578_674_283_873_530_053_378_141_562_551_488_612_664_427_118;
    uint256 constant IC4y =
        7_287_034_513_081_238_828_957_533_263_496_807_963_598_203_055_809_017_390_096_857_850_071_861_275_217;

    uint256 constant IC5x =
        376_609_515_993_600_550_542_915_908_906_611_077_084_465_047_934_410_247_605_458_821_711_682_056_553;
    uint256 constant IC5y =
        6_003_958_724_118_180_001_282_689_434_745_727_924_900_246_989_469_196_981_465_696_408_950_686_281_920;

    uint256 constant IC6x =
        4_114_464_773_898_128_684_017_608_021_640_600_376_825_389_753_898_935_779_412_362_899_461_071_957_347;
    uint256 constant IC6y =
        12_116_827_712_478_685_096_481_303_113_174_675_736_720_853_751_791_558_658_587_967_083_926_491_961_373;

    uint256 constant IC7x =
        11_879_549_657_040_239_155_285_098_668_642_923_764_098_806_705_577_664_172_589_570_817_048_147_499_531;
    uint256 constant IC7y =
        16_364_220_942_428_895_883_830_102_860_650_936_556_652_142_526_901_170_608_390_340_948_090_972_629_233;

    uint256 constant IC8x =
        8_151_481_920_672_778_304_506_547_765_510_008_816_212_770_952_732_323_050_887_736_197_935_250_821_481;
    uint256 constant IC8y =
        15_911_348_925_169_358_262_691_813_348_705_325_730_437_963_862_797_309_737_011_621_024_921_139_811_628;

    uint256 constant IC9x =
        16_247_298_693_679_850_261_366_911_217_289_432_306_734_559_161_112_340_029_022_204_322_111_480_391_852;
    uint256 constant IC9y =
        8_085_690_364_905_380_209_546_505_100_996_200_255_169_066_143_870_601_771_417_802_873_971_888_788_887;

    uint256 constant IC10x =
        11_325_991_220_999_115_887_927_100_875_847_787_805_622_354_787_135_322_722_651_074_499_235_594_115_064;
    uint256 constant IC10y =
        10_921_826_194_596_132_513_334_818_472_244_973_397_397_248_936_023_066_165_237_932_163_264_742_242_945;

    uint256 constant IC11x =
        18_926_396_703_530_199_615_820_966_726_459_143_941_516_192_819_445_514_049_793_403_690_804_433_224_036;
    uint256 constant IC11y =
        9_001_483_814_552_864_214_112_010_511_532_104_499_603_181_678_424_116_256_722_249_234_405_304_790_717;

    uint256 constant IC12x =
        21_076_943_620_442_678_329_584_121_210_756_352_500_492_496_965_307_359_521_446_555_387_263_857_577_437;
    uint256 constant IC12y =
        20_815_964_875_184_161_889_465_644_437_722_750_867_910_674_124_205_544_571_481_986_284_747_792_032_788;

    uint256 constant IC13x =
        21_140_404_147_207_202_899_818_913_068_703_964_496_237_460_606_771_440_781_947_865_039_920_991_809_653;
    uint256 constant IC13y =
        17_875_458_701_740_080_756_803_120_839_506_119_862_084_470_960_047_117_213_431_243_921_547_228_874_700;

    uint256 constant IC14x =
        3_610_218_178_333_827_198_163_194_068_821_017_665_345_314_816_222_458_072_320_505_293_320_125_479_620;
    uint256 constant IC14y =
        16_833_627_683_925_722_835_064_424_539_673_389_551_571_362_965_630_656_248_052_260_068_463_557_327_157;

    // Memory data
    uint16 constant pVk = 0;
    uint16 constant pPairing = 128;

    uint16 constant pLastMem = 896;

    function verifyProof(
        uint256[2] calldata _pA,
        uint256[2][2] calldata _pB,
        uint256[2] calldata _pC,
        uint256[14] calldata _pubSignals
    ) public view returns (bool) {
        assembly {
            function checkField(v) {
                if iszero(lt(v, r)) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            // G1 function to multiply a G1 value(x,y) to value in an address
            function g1_mulAccC(pR, x, y, s) {
                let success
                let mIn := mload(0x40)
                mstore(mIn, x)
                mstore(add(mIn, 32), y)
                mstore(add(mIn, 64), s)

                success := staticcall(sub(gas(), 2000), 7, mIn, 96, mIn, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }

                mstore(add(mIn, 64), mload(pR))
                mstore(add(mIn, 96), mload(add(pR, 32)))

                success := staticcall(sub(gas(), 2000), 6, mIn, 128, pR, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            function checkPairing(pA, pB, pC, pubSignals, pMem) -> isOk {
                let _pPairing := add(pMem, pPairing)
                let _pVk := add(pMem, pVk)

                mstore(_pVk, IC0x)
                mstore(add(_pVk, 32), IC0y)

                // Compute the linear combination vk_x

                g1_mulAccC(_pVk, IC1x, IC1y, calldataload(add(pubSignals, 0)))

                g1_mulAccC(_pVk, IC2x, IC2y, calldataload(add(pubSignals, 32)))

                g1_mulAccC(_pVk, IC3x, IC3y, calldataload(add(pubSignals, 64)))

                g1_mulAccC(_pVk, IC4x, IC4y, calldataload(add(pubSignals, 96)))

                g1_mulAccC(_pVk, IC5x, IC5y, calldataload(add(pubSignals, 128)))

                g1_mulAccC(_pVk, IC6x, IC6y, calldataload(add(pubSignals, 160)))

                g1_mulAccC(_pVk, IC7x, IC7y, calldataload(add(pubSignals, 192)))

                g1_mulAccC(_pVk, IC8x, IC8y, calldataload(add(pubSignals, 224)))

                g1_mulAccC(_pVk, IC9x, IC9y, calldataload(add(pubSignals, 256)))

                g1_mulAccC(_pVk, IC10x, IC10y, calldataload(add(pubSignals, 288)))

                g1_mulAccC(_pVk, IC11x, IC11y, calldataload(add(pubSignals, 320)))

                g1_mulAccC(_pVk, IC12x, IC12y, calldataload(add(pubSignals, 352)))

                g1_mulAccC(_pVk, IC13x, IC13y, calldataload(add(pubSignals, 384)))

                g1_mulAccC(_pVk, IC14x, IC14y, calldataload(add(pubSignals, 416)))

                // -A
                mstore(_pPairing, calldataload(pA))
                mstore(add(_pPairing, 32), mod(sub(q, calldataload(add(pA, 32))), q))

                // B
                mstore(add(_pPairing, 64), calldataload(pB))
                mstore(add(_pPairing, 96), calldataload(add(pB, 32)))
                mstore(add(_pPairing, 128), calldataload(add(pB, 64)))
                mstore(add(_pPairing, 160), calldataload(add(pB, 96)))

                // alpha1
                mstore(add(_pPairing, 192), alphax)
                mstore(add(_pPairing, 224), alphay)

                // beta2
                mstore(add(_pPairing, 256), betax1)
                mstore(add(_pPairing, 288), betax2)
                mstore(add(_pPairing, 320), betay1)
                mstore(add(_pPairing, 352), betay2)

                // vk_x
                mstore(add(_pPairing, 384), mload(add(pMem, pVk)))
                mstore(add(_pPairing, 416), mload(add(pMem, add(pVk, 32))))

                // gamma2
                mstore(add(_pPairing, 448), gammax1)
                mstore(add(_pPairing, 480), gammax2)
                mstore(add(_pPairing, 512), gammay1)
                mstore(add(_pPairing, 544), gammay2)

                // C
                mstore(add(_pPairing, 576), calldataload(pC))
                mstore(add(_pPairing, 608), calldataload(add(pC, 32)))

                // delta2
                mstore(add(_pPairing, 640), deltax1)
                mstore(add(_pPairing, 672), deltax2)
                mstore(add(_pPairing, 704), deltay1)
                mstore(add(_pPairing, 736), deltay2)

                let success := staticcall(sub(gas(), 2000), 8, _pPairing, 768, _pPairing, 0x20)

                isOk := and(success, mload(_pPairing))
            }

            let pMem := mload(0x40)
            mstore(0x40, add(pMem, pLastMem))

            // Validate that all evaluations ∈ F

            checkField(calldataload(add(_pubSignals, 0)))

            checkField(calldataload(add(_pubSignals, 32)))

            checkField(calldataload(add(_pubSignals, 64)))

            checkField(calldataload(add(_pubSignals, 96)))

            checkField(calldataload(add(_pubSignals, 128)))

            checkField(calldataload(add(_pubSignals, 160)))

            checkField(calldataload(add(_pubSignals, 192)))

            checkField(calldataload(add(_pubSignals, 224)))

            checkField(calldataload(add(_pubSignals, 256)))

            checkField(calldataload(add(_pubSignals, 288)))

            checkField(calldataload(add(_pubSignals, 320)))

            checkField(calldataload(add(_pubSignals, 352)))

            checkField(calldataload(add(_pubSignals, 384)))

            checkField(calldataload(add(_pubSignals, 416)))

            // Validate all evaluations
            let isValid := checkPairing(_pA, _pB, _pC, _pubSignals, pMem)

            mstore(0, isValid)
            return(0, 0x20)
        }
    }
}
